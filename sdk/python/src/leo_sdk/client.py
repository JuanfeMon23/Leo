"""Cliente HTTP (async) del protocolo de Leo, con client auth HTTP Basic.

Leo no ve la prueba DPoP del navegador: el BFF la verifica (`leo_sdk.dpop`) y
pasa el `jkt` en estas llamadas.
"""

from typing import Any
from uuid import UUID

import httpx

from leo_sdk.errors import LeoUnavailableError, error_from_response
from leo_sdk.models import Introspection, ServiceToken, TokenSet
from leo_sdk.settings import LeoSettings


class LeoClient:
    def __init__(
        self, settings: LeoSettings, *, http: httpx.AsyncClient | None = None
    ) -> None:
        """`http` permite inyectar un cliente (tests, proxies); si se omite se
        crea uno propio que `aclose()` cierra."""
        self.settings = settings
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(timeout=settings.http_timeout_seconds)
        self._base = settings.leo_api_url.rstrip("/")
        self._auth = httpx.BasicAuth(
            settings.app_client_id, settings.app_client_secret.get_secret_value()
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _request(
        self, method: str, path: str, *, json: Any = None
    ) -> httpx.Response:
        try:
            response = await self._http.request(
                method, f"{self._base}{path}", json=json, auth=self._auth
            )
        except httpx.HTTPError as exc:  # red, timeout, DNS...
            raise LeoUnavailableError(details=type(exc).__name__) from exc
        if response.is_success:
            return response
        try:
            payload = response.json()
        except ValueError:
            payload = None
        retry_after = response.headers.get("retry-after", "")
        raise error_from_response(
            response.status_code,
            payload,
            retry_after=int(retry_after) if retry_after.isdigit() else None,
        )

    async def exchange_code(
        self, code: str, code_verifier: str, redirect_uri: str, jkt: str
    ) -> TokenSet:
        response = await self._request(
            "POST",
            "/auth/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "jkt": jkt,
            },
        )
        return TokenSet.model_validate(response.json())

    async def refresh(self, refresh_token: str, jkt: str) -> TokenSet:
        response = await self._request(
            "POST",
            "/auth/token",
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "jkt": jkt,
            },
        )
        return TokenSet.model_validate(response.json())

    async def introspect(self, token: str, jkt: str) -> Introspection:
        response = await self._request(
            "POST", "/auth/introspect", json={"token": token, "jkt": jkt}
        )
        return Introspection.model_validate(response.json())

    async def introspect_service(self, token: str) -> Introspection:
        """Introspecciona un token de servicio (sin `jkt`). Solo responde
        `active` si ESTA app es la audiencia del token."""
        response = await self._request(
            "POST", "/auth/introspect", json={"token": token}
        )
        return Introspection.model_validate(response.json())

    async def client_credentials(self, audience: str) -> ServiceToken:
        """Canjea las credenciales de la app por un token de servicio hacia
        `audience` (slug de la app destino)."""
        response = await self._request(
            "POST",
            "/auth/token",
            json={"grant_type": "client_credentials", "audience": audience},
        )
        return ServiceToken.model_validate(response.json())

    async def revoke(self, token: str, jkt: str) -> None:
        await self._request("POST", "/auth/revoke", json={"token": token, "jkt": jkt})

    async def sync_catalog(self, payload: dict[str, Any]) -> dict[str, Any]:
        slug = self.settings.app_client_id
        response = await self._request(
            "PUT", f"/applications/{slug}/catalog", json=payload
        )
        return response.json()

    async def ingest_audit(self, payload: dict[str, Any]) -> UUID:
        response = await self._request("POST", "/audit/events", json=payload)
        return UUID(response.json()["id"])
