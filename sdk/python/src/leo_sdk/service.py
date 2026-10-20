"""Lado consumidor de las credenciales de servicio: obtiene (y cachea en
memoria) el token de servicio por audiencia y lo aplica a un `httpx.AsyncClient`.

Nunca se loguea el token ni el secreto.
"""

import asyncio
import time
from collections.abc import AsyncGenerator, Callable

import httpx

from leo_sdk.client import LeoClient

DEFAULT_MARGIN_SECONDS = 30.0


class ServiceTokenProvider:
    """Token de servicio por audiencia (slug de la app destino).

    - Cachea hasta `margin_seconds` antes de `expires_in` (si el token vive menos
      que el margen, usa la mitad de su vida).
    - Un solo canje concurrente por audiencia; los errores no se cachean.
    - Los tokens viven solo en memoria de este proceso.
    """

    def __init__(
        self,
        client: LeoClient,
        *,
        margin_seconds: float = DEFAULT_MARGIN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._margin = margin_seconds
        self._clock = clock
        self._tokens: dict[str, tuple[str, float]] = {}  # audiencia -> (token, vence)
        self._locks: dict[str, asyncio.Lock] = {}

    async def token(self, audience: str, *, stale: str | None = None) -> str:
        """Token vigente para `audience`. `stale` es un token que el destino
        rechazo: si sigue siendo el de la cache se descarta y se canjea otro."""
        cached = self._fresh(audience, stale)
        if cached is not None:
            return cached
        lock = self._locks.setdefault(audience, asyncio.Lock())
        async with lock:
            cached = self._fresh(audience, stale)  # otro ya lo canjeo
            if cached is not None:
                return cached
            issued = await self._client.client_credentials(audience)
            margin = min(self._margin, issued.expires_in / 2)
            self._tokens[audience] = (
                issued.access_token,
                self._clock() + issued.expires_in - margin,
            )
            return issued.access_token

    def _fresh(self, audience: str, stale: str | None) -> str | None:
        entry = self._tokens.get(audience)
        if entry is None:
            return None
        token, expires = entry
        if token == stale or expires <= self._clock():
            self._tokens.pop(audience, None)
            return None
        return token

    async def headers(self, audience: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self.token(audience)}"}

    def invalidate(self, audience: str | None = None) -> None:
        """Olvida el token de una audiencia (o todos)."""
        if audience is None:
            self._tokens.clear()
        else:
            self._tokens.pop(audience, None)

    def auth(self, audience: str) -> "ServiceAuth":
        """`httpx.Auth` para `httpx.AsyncClient(auth=provider.auth("destino"))`."""
        return ServiceAuth(self, audience)


class ServiceAuth(httpx.Auth):
    """Agrega `Authorization: Bearer` y, si el destino responde 401, reintenta
    UNA vez con un token nuevo."""

    requires_response_body = False

    def __init__(self, provider: ServiceTokenProvider, audience: str) -> None:
        self._provider = provider
        self._audience = audience

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await self._provider.token(self._audience)
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code == 401:
            token = await self._provider.token(self._audience, stale=token)
            request.headers["Authorization"] = f"Bearer {token}"
            yield request


__all__ = ["ServiceAuth", "ServiceTokenProvider"]
