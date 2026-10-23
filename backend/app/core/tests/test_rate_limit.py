"""Limitador de ventana deslizante: contrato comun a los dos almacenes
(memoria y PostgreSQL), atomicidad bajo concurrencia, limpieza de filas
vencidas y seleccion por `LEO_RATE_LIMIT_BACKEND`."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core import clock, rate_limit
from app.core.config import Settings, get_settings
from app.core.db.tests.conftest import TEST_URL, migrated  # noqa: F401
from app.core.rate_limit import (
    MemoryRateLimitStore,
    PostgresRateLimitStore,
    SlidingWindowLimiter,
    make_limiter,
)


@pytest_asyncio.fixture
async def pg_engine(migrated: None) -> AsyncGenerator[AsyncEngine]:  # noqa: F811
    engine = create_async_engine(TEST_URL, poolclass=pool.NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(params=["memory", "postgres"])
async def limiter_factory(request, pg_engine: AsyncEngine):
    """Fabrica de limitadores sobre cada almacen, con bucket propio por test."""
    created: list[SlidingWindowLimiter] = []

    def make(limit: int, window: int = 60) -> SlidingWindowLimiter:
        store = (
            MemoryRateLimitStore()
            if request.param == "memory"
            else PostgresRateLimitStore(pg_engine)
        )
        limiter = SlidingWindowLimiter(
            limit, window, bucket=f"test-{uuid4().hex[:12]}", store=store
        )
        created.append(limiter)
        return limiter

    yield make
    for limiter in created:
        await limiter.reset()


async def test_ventana_deslizante(limiter_factory) -> None:
    limiter = limiter_factory(2)
    now = clock.now()
    await limiter.hit("k", now)
    assert await limiter.retry_after("k", now) == 0
    await limiter.hit("k", now)
    assert 0 < await limiter.retry_after("k", now) <= 61
    assert await limiter.retry_after("k", now + timedelta(seconds=61)) == 0
    assert await limiter.retry_after("otra", now) == 0


async def test_check_and_hit_registra_solo_si_hay_cupo(limiter_factory) -> None:
    limiter = limiter_factory(2)
    now = clock.now()
    assert await limiter.check_and_hit("k", now) == 0
    assert await limiter.check_and_hit("k", now) == 0
    wait = await limiter.check_and_hit("k", now)
    assert 0 < wait <= 61
    # El intento rechazado no se registro: pasada la ventana hay cupo completo.
    later = now + timedelta(seconds=61)
    assert await limiter.check_and_hit("k", later) == 0
    assert await limiter.check_and_hit("k", later) == 0
    assert await limiter.check_and_hit("k", later) > 0


async def test_la_espera_cuenta_desde_el_acierto_mas_antiguo(limiter_factory) -> None:
    limiter = limiter_factory(2, window=60)
    now = clock.now()
    await limiter.hit("k", now)
    await limiter.hit("k", now + timedelta(seconds=30))
    assert await limiter.retry_after("k", now + timedelta(seconds=40)) == 21
    # Al vencer el primero queda cupo aunque el segundo siga vigente.
    assert await limiter.retry_after("k", now + timedelta(seconds=61)) == 0


async def test_reset_por_clave_y_total(limiter_factory) -> None:
    limiter = limiter_factory(1)
    now = clock.now()
    await limiter.hit("a", now)
    await limiter.hit("b", now)
    await limiter.reset("a")
    assert await limiter.retry_after("a", now) == 0
    assert await limiter.retry_after("b", now) > 0
    await limiter.reset()
    assert await limiter.retry_after("b", now) == 0


async def test_buckets_distintos_no_se_mezclan(limiter_factory) -> None:
    uno, otro = limiter_factory(1), limiter_factory(1)
    now = clock.now()
    await uno.hit("k", now)
    assert await uno.retry_after("k", now) > 0
    assert await otro.retry_after("k", now) == 0


async def test_concurrencia_no_deja_pasar_mas_del_limite(limiter_factory) -> None:
    limiter = limiter_factory(5)
    now = clock.now()
    waits = await asyncio.gather(*(limiter.check_and_hit("k", now) for _ in range(40)))
    assert waits.count(0) == 5
    assert all(w > 0 for w in waits if w)


async def test_dos_procesos_comparten_el_conteo(pg_engine: AsyncEngine) -> None:
    """Dos almacenes con motores propios (como dos procesos) cuentan juntos."""
    other = create_async_engine(TEST_URL, poolclass=pool.NullPool)
    bucket = f"test-{uuid4().hex[:12]}"
    a = SlidingWindowLimiter(
        3, 60, bucket=bucket, store=PostgresRateLimitStore(pg_engine)
    )
    b = SlidingWindowLimiter(3, 60, bucket=bucket, store=PostgresRateLimitStore(other))
    try:
        now = clock.now()
        waits = await asyncio.gather(
            *(limiter.check_and_hit("ip", now) for limiter in [a, b] * 5)
        )
        assert waits.count(0) == 3
    finally:
        await a.reset()
        await other.dispose()


async def _count(engine: AsyncEngine, bucket: str) -> int:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text("SELECT count(*) FROM rate_limit_hits WHERE bucket = :b"),
                {"b": bucket},
            )
        ).scalar_one()


async def test_postgres_borra_vencidas_de_la_clave_al_consultar(
    pg_engine: AsyncEngine,
) -> None:
    store = PostgresRateLimitStore(pg_engine)
    bucket = f"test-{uuid4().hex[:12]}"
    now = clock.now()
    await store.hit(bucket, "k", 60, now - timedelta(seconds=120))
    assert await store.check_and_hit(bucket, "k", 1, 60, now) == 0
    assert await _count(pg_engine, bucket) == 1
    await store.reset(bucket)


async def test_postgres_purge_expired_limpia_el_bucket(pg_engine: AsyncEngine) -> None:
    store = PostgresRateLimitStore(pg_engine)
    bucket = f"test-{uuid4().hex[:12]}"
    now = clock.now()
    await store.hit(bucket, "vieja", 60, now - timedelta(seconds=120))
    await store.hit(bucket, "otra-vieja", 60, now - timedelta(seconds=90))
    await store.hit(bucket, "vigente", 60, now)
    assert await _count(pg_engine, bucket) == 3
    assert await store.purge_expired(bucket, 60, now) == 2
    assert await _count(pg_engine, bucket) == 1
    await store.reset(bucket)


async def test_make_limiter_usa_memoria_por_defecto() -> None:
    assert get_settings().leo_rate_limit_backend == "memory"
    limiter = make_limiter("test-default", 1, 60)
    assert isinstance(limiter.store, MemoryRateLimitStore)


async def test_make_limiter_con_backend_postgres(monkeypatch) -> None:
    settings = get_settings().model_copy(update={"leo_rate_limit_backend": "postgres"})
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    monkeypatch.setattr(rate_limit, "_postgres_store", None)
    limiter = make_limiter("test-pg", 1, 60)
    assert isinstance(limiter.store, PostgresRateLimitStore)


def test_backend_invalido_falla_al_arrancar() -> None:
    base = get_settings().model_dump()
    with pytest.raises(ValidationError):
        Settings(**{**base, "leo_rate_limit_backend": "redis"})
