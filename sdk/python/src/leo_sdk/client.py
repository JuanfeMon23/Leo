"""Cliente HTTP (async) del protocolo de Leo, con client auth HTTP Basic.

Leo no ve la prueba DPoP del navegador: el BFF la verifica (`leo_sdk.dpop`) y
pasa el `jkt` en estas llamadas.
"""

import time
from typing import Any
from uuid import UUID

import httpx

from leo_sdk.errors import InvalidTokenError, LeoUnavailableError, error_from_response
from leo_sdk.models import (
    Introspection,
    PasswordPolicy,
    ServiceToken,
    TokenSet,
    UserProfile,
)
from leo_sdk.settings import LeoSettings

POLICY_CACHE_SECONDS = 30.0


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
        self._service_tokens: Any = None  # ServiceTokenProvider, perezoso
        self._policy: tuple[float, PasswordPolicy] | None = None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        bearer: str | None = None,
        public: bool = False,
    ) -> httpx.Response:
        """Con `bearer` la llamada va con `Authorization: Bearer` (token de
        servicio) en vez de HTTP Basic; `public` = endpoint sin credenciales."""
        try:
            response = await self._http.request(
                method,
                f"{self._base}{path}",
                json=json,
                auth=self._auth if bearer is None and not public else None,
                headers={"Authorization": f"Bearer {bearer}"} if bearer else None,
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

    async def password_policy(self) -> PasswordPolicy:
        """Politica de contrasenas vigente (endpoint publico, sin credenciales).
        Se guarda 30 s en memoria para no consultar a Leo en cada validacion."""
        now = time.monotonic()
        if self._policy and now - self._policy[0] < POLICY_CACHE_SECONDS:
            return self._policy[1]
        response = await self._request("GET", "/auth/password-policy", public=True)
        policy = PasswordPolicy.model_validate(response.json())
        self._policy = (now, policy)
        return policy

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

    async def _as_service(
        self, method: str, path: str, body: dict[str, Any]
    ) -> httpx.Response:
        """Llamada a Leo con token de servicio (audiencia `leo`, cacheado). Un
        401 del token de SERVICIO renueva el token y reintenta una vez; el 401
        por el token del usuario no se reintenta (`InvalidTokenError`)."""
        if self._service_tokens is None:
            from leo_sdk.service import ServiceTokenProvider  # evita el ciclo

            self._service_tokens = ServiceTokenProvider(self)
        token = await self._service_tokens.token("leo")
        try:
            return await self._request(method, path, json=body, bearer=token)
        except InvalidTokenError as exc:
            if exc.is_user_token:
                raise
            token = await self._service_tokens.token("leo", stale=token)
            return await self._request(method, path, json=body, bearer=token)

    async def update_user_profile(
        self,
        user_access_token: str,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        current_password: str | None = None,
    ) -> UserProfile:
        """Edita nombres/correo del usuario dueno de `user_access_token` (el
        access token que Leo emitio a ESTA app). Requiere el rol de servicio
        `leo-self-service-delegate` y un usuario sin permisos `leo.*`. Cambiar
        a otro correo exige `current_password` (422 `current_password_required`,
        403 `invalid_current_password`, 429 `TooManyAttemptsError`, 409
        `duplicate`). Solo se envian los campos que no son None."""
        body: dict[str, Any] = {"user_access_token": user_access_token}
        for name, value in (
            ("first_name", first_name),
            ("last_name", last_name),
            ("email", email),
            ("current_password", current_password),
        ):
            if value is not None:
                body[name] = value
        response = await self._as_service(
            "PATCH", "/users/service/delegated/profile", body
        )
        return UserProfile.model_validate(response.json())

    async def change_user_password(
        self, user_access_token: str, current_password: str, new_password: str
    ) -> None:
        """Cambia la contrasena del usuario dueno de `user_access_token`; Leo
        cierra sus demas sesiones. Errores: 401 `invalid_credentials`, 422
        `weak_password`/`same_password`, 429 `TooManyAttemptsError`."""
        await self._as_service(
            "POST",
            "/users/service/delegated/password",
            {
                "user_access_token": user_access_token,
                "current_password": current_password,
                "new_password": new_password,
            },
        )
