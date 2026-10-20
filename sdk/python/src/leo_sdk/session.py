"""Sesion del BFF sin dependencia de FastAPI: verificacion de la prueba DPoP,
introspeccion con cache y refresh sin carreras."""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from leo_sdk.cache import TTLCache
from leo_sdk.client import LeoClient
from leo_sdk.crypto import constant_time_equals, sha256_hex
from leo_sdk.dpop import (
    DpopError,
    DpopProof,
    InMemoryReplayStore,
    ReplayStore,
    expected_htu,
    verify_dpop_proof,
)
from leo_sdk.errors import InvalidClientError, LeoError, LeoUnavailableError
from leo_sdk.models import LeoUser, TokenSet

logger = logging.getLogger("leo_sdk.session")

REFRESH_DEDUP_SECONDS = 10.0


@dataclass(frozen=True)
class _CachedUser:
    jkt: str
    user: LeoUser
    exp: float


class SessionManager:
    def __init__(
        self,
        client: LeoClient,
        *,
        replay_store: ReplayStore | None = None,
        wall_clock: Callable[[], float] = time.time,
        cache_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.settings = client.settings
        self._replay = replay_store or InMemoryReplayStore()
        self._wall = wall_clock
        self._cache: TTLCache[_CachedUser] = TTLCache(
            self.settings.introspection_ttl_seconds, clock=cache_clock
        )
        # Refresh concurrente de un mismo navegador: un solo canje (un segundo
        # canje con el mismo refresh se leeria como reuso y mataria la sesion).
        self._recent: TTLCache[tuple[str, TokenSet]] = TTLCache(
            REFRESH_DEDUP_SECONDS, clock=cache_clock
        )
        self._inflight: dict[str, asyncio.Task[TokenSet]] = {}

    # --- DPoP ---

    async def verify_proof(
        self, method: str, path: str, proof: str | None
    ) -> DpopProof:
        htu = expected_htu(self.settings.public_url, path)
        return await verify_dpop_proof(
            proof, htm=method, htu=htu, store=self._replay, now=self._wall()
        )

    # --- introspeccion ---

    async def user_for(
        self, access_token: str, jkt: str, *, use_cache: bool = True
    ) -> LeoUser | None:
        """Usuario del access token o None si esta inactivo. Con cache (30 s por
        defecto) salvo heartbeat (`use_cache=False`), que ademas desliza la
        inactividad en Leo."""
        key = sha256_hex(access_token)
        now = self._wall()
        if use_cache:
            hit = self._cache.get(key)
            if hit and constant_time_equals(hit.jkt, jkt) and hit.exp > now:
                return hit.user
        try:
            intro = await self.client.introspect(access_token, jkt)
        except InvalidClientError as exc:
            raise self._misconfigured(exc) from exc
        if not intro.active or intro.user is None or intro.session_id is None:
            self._cache.delete(key)
            return None
        user = LeoUser(
            id=intro.user.id,
            username=intro.user.username,
            name=intro.user.name,
            email=intro.user.email,
            permissions=frozenset(intro.permissions),
            session_id=intro.session_id,
            first_name=intro.user.first_name or intro.user.name,
            last_name=intro.user.last_name or "",
            applications=tuple(intro.applications),
            expires_at=(datetime.fromtimestamp(intro.exp, UTC) if intro.exp else None),
            # Si Leo aun no envia `last_activity_at`, la introspeccion misma
            # (que desliza la inactividad) marca la ultima actividad.
            last_activity_at=intro.last_activity_at or datetime.fromtimestamp(now, UTC),
            idle_timeout_seconds=intro.idle_timeout_seconds,
            access_token=access_token,
            jkt=jkt,
        )
        self._cache.set(key, _CachedUser(jkt, user, float(intro.exp or now + 1)))
        return user

    def forget(self, access_token: str | None) -> None:
        """Invalida la cache de ese token (logout)."""
        if access_token:
            self._cache.delete(sha256_hex(access_token))

    # --- refresh ---

    async def refresh(self, refresh_token: str, jkt: str) -> TokenSet:
        key = f"{sha256_hex(refresh_token)}:{jkt}"
        recent = self._recent.get(key)
        if recent:
            return recent[1]
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.ensure_future(self._do_refresh(key, refresh_token, jkt))
            self._inflight[key] = task
        return await asyncio.shield(task)

    async def _do_refresh(self, key: str, refresh_token: str, jkt: str) -> TokenSet:
        try:
            tokens = await self.client.refresh(refresh_token, jkt)
            self._recent.set(key, (jkt, tokens))
            return tokens
        except InvalidClientError as exc:
            raise self._misconfigured(exc) from exc
        finally:
            self._inflight.pop(key, None)

    @staticmethod
    def _misconfigured(exc: LeoError) -> LeoUnavailableError:
        logger.error("Leo rechazó las credenciales de la app (%s).", exc.code)
        return LeoUnavailableError(
            "La aplicación no está bien configurada ante Leo. Avisa a un administrador."
        )


__all__ = ["DpopError", "SessionManager"]
