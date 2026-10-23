"""Limitador de ventana deslizante con almacen intercambiable.

Contrato (async) para quien lo usa: `retry_after(key, at)` (segundos hasta
poder reintentar; 0 si no esta limitado), `hit(key, at)` (registra un
intento), `check_and_hit(key, at)` (atomico: si hay cupo registra el intento
y devuelve 0; si no, devuelve la espera sin registrar) y `reset(key)`. Para
"un solo limitador, un solo intento" usar `check_and_hit`: `retry_after` +
`hit` por separado dejan pasar a dos peticiones concurrentes.

Almacenes (`RateLimitStore`), elegidos con `LEO_RATE_LIMIT_BACKEND`:
- `memory` (default, dev): por proceso. Con varios procesos cada uno cuenta
  por separado, asi que NO sirve en produccion.
- `postgres` (produccion): tabla `rate_limit_hits`, compartida entre
  procesos. Atomico con un advisory lock transaccional por (bucket, clave).
  Usa su propia conexion y commit, independientes de la sesion del request
  (los intentos fallidos cuentan aunque el request haga rollback). El reloj
  es el del proceso que llama: mantenerlos sincronizados (NTP).

Cada limitador tiene un `bucket` (nombre) para no mezclar claves en la tabla.
"""

import random
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core import clock

# Probabilidad de purgar, en cada acierto, las filas vencidas de todo el
# bucket (las claves que no vuelven a consultarse nunca se limpiarian si no).
_PURGE_PROBABILITY = 0.02


def _wait(oldest: float, window_seconds: int, now: float) -> int:
    return int(oldest + window_seconds - now) + 1


class RateLimitStore(Protocol):
    async def retry_after(
        self, bucket: str, key: str, limit: int, window_seconds: int, now: datetime
    ) -> int: ...

    async def hit(
        self, bucket: str, key: str, window_seconds: int, now: datetime
    ) -> None: ...

    async def check_and_hit(
        self, bucket: str, key: str, limit: int, window_seconds: int, now: datetime
    ) -> int: ...

    async def reset(self, bucket: str, key: str | None = None) -> None: ...


class MemoryRateLimitStore:
    """Por proceso; seguro entre hilos."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(
        self, bucket: str, key: str, window_seconds: int, now: float
    ) -> deque[float]:
        hits = self._hits.get((bucket, key))
        if hits is None:
            return deque()
        while hits and hits[0] <= now - window_seconds:
            hits.popleft()
        if not hits:
            del self._hits[(bucket, key)]
            return deque()
        return hits

    async def retry_after(
        self, bucket: str, key: str, limit: int, window_seconds: int, now: datetime
    ) -> int:
        ts = now.timestamp()
        with self._lock:
            hits = self._recent(bucket, key, window_seconds, ts)
            return 0 if len(hits) < limit else _wait(hits[0], window_seconds, ts)

    async def hit(
        self, bucket: str, key: str, window_seconds: int, now: datetime
    ) -> None:
        ts = now.timestamp()
        with self._lock:
            self._recent(bucket, key, window_seconds, ts)
            self._hits.setdefault((bucket, key), deque()).append(ts)

    async def check_and_hit(
        self, bucket: str, key: str, limit: int, window_seconds: int, now: datetime
    ) -> int:
        ts = now.timestamp()
        with self._lock:
            hits = self._recent(bucket, key, window_seconds, ts)
            if len(hits) >= limit:
                return _wait(hits[0], window_seconds, ts)
            self._hits.setdefault((bucket, key), deque()).append(ts)
            return 0

    async def reset(self, bucket: str, key: str | None = None) -> None:
        with self._lock:
            if key is not None:
                self._hits.pop((bucket, key), None)
                return
            for k in [k for k in self._hits if k[0] == bucket]:
                del self._hits[k]


_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"
_DELETE_EXPIRED = (
    "DELETE FROM rate_limit_hits "
    "WHERE bucket = :bucket AND key = :key AND hit_at <= :cutoff"
)
_STATS = (
    "SELECT count(*), min(hit_at) FROM rate_limit_hits "
    "WHERE bucket = :bucket AND key = :key AND hit_at > :cutoff"
)
_INSERT = (
    "INSERT INTO rate_limit_hits (bucket, key, hit_at) VALUES (:bucket, :key, :now)"
)


class PostgresRateLimitStore:
    """Compartido entre procesos (tabla `rate_limit_hits`, migracion 0006)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @staticmethod
    def _params(
        bucket: str, key: str, window_seconds: int, now: datetime
    ) -> dict[str, Any]:
        return {
            "bucket": bucket,
            "key": key,
            "cutoff": now - timedelta(seconds=window_seconds),
            "now": now,
            "lock_key": f"rate_limit:{bucket}:{key}",
        }

    @staticmethod
    async def _stats(
        conn: AsyncConnection, params: dict[str, Any]
    ) -> tuple[int, datetime | None]:
        row = (await conn.execute(text(_STATS), params)).one()
        return row[0], row[1]

    async def retry_after(
        self, bucket: str, key: str, limit: int, window_seconds: int, now: datetime
    ) -> int:
        params = self._params(bucket, key, window_seconds, now)
        async with self._engine.connect() as conn:
            count, oldest = await self._stats(conn, params)
        if count < limit or oldest is None:
            return 0
        return _wait(oldest.timestamp(), window_seconds, now.timestamp())

    async def hit(
        self, bucket: str, key: str, window_seconds: int, now: datetime
    ) -> None:
        params = self._params(bucket, key, window_seconds, now)
        async with self._engine.begin() as conn:
            await conn.execute(text(_LOCK), params)
            await conn.execute(text(_DELETE_EXPIRED), params)
            await conn.execute(text(_INSERT), params)
        await self._maybe_purge(bucket, window_seconds, now)

    async def check_and_hit(
        self, bucket: str, key: str, limit: int, window_seconds: int, now: datetime
    ) -> int:
        params = self._params(bucket, key, window_seconds, now)
        wait = 0
        async with self._engine.begin() as conn:
            await conn.execute(text(_LOCK), params)
            await conn.execute(text(_DELETE_EXPIRED), params)
            count, oldest = await self._stats(conn, params)
            if count < limit or oldest is None:
                await conn.execute(text(_INSERT), params)
            else:
                wait = _wait(oldest.timestamp(), window_seconds, now.timestamp())
        if not wait:
            await self._maybe_purge(bucket, window_seconds, now)
        return wait

    async def reset(self, bucket: str, key: str | None = None) -> None:
        sql = "DELETE FROM rate_limit_hits WHERE bucket = :bucket"
        params: dict[str, Any] = {"bucket": bucket}
        if key is not None:
            sql += " AND key = :key"
            params["key"] = key
        async with self._engine.begin() as conn:
            await conn.execute(text(sql), params)

    async def purge_expired(
        self, bucket: str, window_seconds: int, now: datetime
    ) -> int:
        """Borra las filas vencidas de todo el bucket; devuelve cuantas."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "DELETE FROM rate_limit_hits "
                    "WHERE bucket = :bucket AND hit_at <= :cutoff"
                ),
                {
                    "bucket": bucket,
                    "cutoff": now - timedelta(seconds=window_seconds),
                },
            )
        return result.rowcount

    async def _maybe_purge(
        self, bucket: str, window_seconds: int, now: datetime
    ) -> None:
        if random.random() < _PURGE_PROBABILITY:
            await self.purge_expired(bucket, window_seconds, now)


class SlidingWindowLimiter:
    """Limitador de un `bucket`. `limit` y `window_seconds` del constructor son
    solo valores por defecto: cada llamada puede pasar los suyos (`limit=`,
    `window_seconds=`), asi la politica se lee de `settings` en cada peticion y
    un cambio aplica sin reiniciar."""

    def __init__(
        self,
        limit: int | None = None,
        window_seconds: int | None = None,
        *,
        bucket: str = "default",
        store: RateLimitStore | None = None,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.bucket = bucket
        self.store: RateLimitStore = store or MemoryRateLimitStore()

    def _limit(self, limit: int | None) -> int:
        value = self.limit if limit is None else limit
        if value is None:
            raise ValueError(f"El limitador «{self.bucket}» no tiene límite definido.")
        return value

    def _window(self, window_seconds: int | None) -> int:
        value = self.window_seconds if window_seconds is None else window_seconds
        if value is None:
            raise ValueError(f"El limitador «{self.bucket}» no tiene ventana definida.")
        return value

    async def retry_after(
        self,
        key: str,
        at: datetime | None = None,
        *,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> int:
        """Segundos hasta poder volver a intentar; 0 si no esta limitado."""
        return await self.store.retry_after(
            self.bucket,
            key,
            self._limit(limit),
            self._window(window_seconds),
            at or clock.now(),
        )

    async def hit(
        self,
        key: str,
        at: datetime | None = None,
        *,
        window_seconds: int | None = None,
    ) -> None:
        await self.store.hit(
            self.bucket, key, self._window(window_seconds), at or clock.now()
        )

    async def check_and_hit(
        self,
        key: str,
        at: datetime | None = None,
        *,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> int:
        """Atomico: 0 y registra el intento si hay cupo; si no, la espera."""
        return await self.store.check_and_hit(
            self.bucket,
            key,
            self._limit(limit),
            self._window(window_seconds),
            at or clock.now(),
        )

    async def reset(self, key: str | None = None) -> None:
        await self.store.reset(self.bucket, key)


_postgres_store: PostgresRateLimitStore | None = None


def _store_for_settings() -> RateLimitStore | None:
    """`None` = memoria (cada limitador crea la suya); si no, el almacen
    compartido en PostgreSQL, sobre el engine de la app."""
    from app.core.config import get_settings

    if get_settings().leo_rate_limit_backend != "postgres":
        return None
    global _postgres_store
    if _postgres_store is None:
        from app.core.database import engine

        _postgres_store = PostgresRateLimitStore(engine)
    return _postgres_store


def make_limiter(
    bucket: str, limit: int | None = None, window_seconds: int | None = None
) -> SlidingWindowLimiter:
    """Limitador del backend configurado (`LEO_RATE_LIMIT_BACKEND`). Sin
    `limit`/`window_seconds` (lo normal), cada llamada los pasa."""
    return SlidingWindowLimiter(
        limit, window_seconds, bucket=bucket, store=_store_for_settings()
    )
