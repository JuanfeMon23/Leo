"""Integracion FastAPI: `LeoAuth` (usuario actual, `require_action`) y el
router de login BFF (`leo_router`).

Convenciones:
- Toda peticion de usuario lleva la cookie de access + el header `DPoP` con la
  prueba del navegador (se verifica aqui y su `jkt` se pasa a Leo).
- Una app llamadora (servicio) lleva `Authorization: Bearer <token de
  servicio>` (sin cookie ni DPoP): ver `leo_sdk.service`. Son caminos
  distintos: un Bearer invalido nunca cae a la cookie.
- Los errores salen como `{code, message, details}`; hay que llamar a
  `LeoAuth.install(app)` para registrar el handler.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse

from leo_sdk.audit import AuditClient
from leo_sdk.catalog import Catalog, CatalogMismatchError
from leo_sdk.client import LeoClient
from leo_sdk.crypto import constant_time_equals
from leo_sdk.dpop import DPOP_HEADER, DpopError, DpopProof, ReplayStore
from leo_sdk.errors import InvalidGrantError, LeoError
from leo_sdk.models import LeoUser, TokenSet
from leo_sdk.oauth import (
    FlowCookie,
    FlowCookieError,
    build_authorize_url,
    new_flow,
)
from leo_sdk.session import SessionManager
from leo_sdk.settings import LeoSettings
from leo_sdk.tags import validate_tag

logger = logging.getLogger("leo_sdk.fastapi")

_PROOF_ATTR = "leo_proof"
_PROOF_ERROR = (
    "Falta la prueba de posesión del dispositivo (DPoP) o no es válida. "
    "Recarga la página e intenta de nuevo."
)


def _not_authenticated() -> LeoError:
    return LeoError("not_authenticated", "Inicia sesión para continuar.", 401)


def _session_expired() -> LeoError:
    return LeoError(
        "session_expired",
        "Tu sesión terminó. Inicia sesión de nuevo.",
        401,
        clear_cookies=True,
    )


class LeoAuth:
    def __init__(
        self,
        settings: LeoSettings | None = None,
        *,
        catalog: Catalog | None = None,
        client: LeoClient | None = None,
        replay_store: ReplayStore | None = None,
    ) -> None:
        self.settings = settings or LeoSettings()  # type: ignore[call-arg]
        self.client = client or LeoClient(self.settings)
        self.sessions = SessionManager(self.client, replay_store=replay_store)
        self.audit = AuditClient(self.client)
        self.catalog = catalog
        self.used_tags: set[str] = set()
        secret = self.settings.state_secret or self.settings.app_client_secret
        self._flow = FlowCookie(
            b"leo-sdk/flow/v1:" + secret.get_secret_value().encode("utf-8"),
            ttl_seconds=self.settings.flow_ttl_seconds,
        )

    # --- ciclo de vida / errores ---

    async def aclose(self) -> None:
        await self.client.aclose()

    def install(self, app: FastAPI) -> None:
        """Registra el handler de `LeoError` (cuerpo `{code, message, details}`
        y borrado de cookies cuando corresponde)."""

        async def handler(_request: Request, exc: Exception) -> JSONResponse:
            assert isinstance(exc, LeoError)
            response = JSONResponse(exc.body(), status_code=exc.status_code)
            if exc.status_code == 401:
                response.headers["WWW-Authenticate"] = (
                    exc.www_authenticate or 'DPoP algs="ES256"'
                )
            if exc.clear_cookies:
                self.clear_session_cookies(response)
            return response

        app.add_exception_handler(LeoError, handler)

    # --- cookies ---

    def _cookie(self, base: str) -> str:
        return self.settings.cookie_name(base)

    def _set_cookie(
        self, response: Response, base: str, value: str, max_age: int
    ) -> None:
        response.set_cookie(
            self._cookie(base),
            value,
            max_age=max_age,
            path=self.settings.cookie_path,
            secure=self.settings.cookie_secure,
            httponly=True,
            samesite="strict",
        )

    def _delete_cookie(self, response: Response, base: str) -> None:
        response.delete_cookie(
            self._cookie(base),
            path=self.settings.cookie_path,
            secure=self.settings.cookie_secure,
            httponly=True,
            samesite="strict",
        )

    def set_session_cookies(self, response: Response, tokens: TokenSet) -> None:
        s = self.settings
        self._set_cookie(
            response, s.access_cookie_name, tokens.access_token, tokens.expires_in
        )
        self._set_cookie(
            response,
            s.refresh_cookie_name,
            tokens.refresh_token,
            tokens.refresh_expires_in,
        )

    def clear_session_cookies(self, response: Response) -> None:
        self._delete_cookie(response, self.settings.access_cookie_name)
        self._delete_cookie(response, self.settings.refresh_cookie_name)

    # --- DPoP de la peticion ---

    async def proof(self, request: Request) -> DpopProof:
        """Prueba DPoP verificada de la peticion (una sola vez por peticion)."""
        cached = getattr(request.state, _PROOF_ATTR, None)
        if cached is not None:
            return cached
        headers = request.headers.getlist(DPOP_HEADER)
        try:
            if len(headers) > 1:
                raise DpopError("más de un header DPoP")
            result = await self.sessions.verify_proof(
                request.method, request.url.path, headers[0] if headers else None
            )
        except DpopError as exc:
            logger.info("Prueba DPoP rechazada: %s", exc.reason)
            raise LeoError("invalid_dpop_proof", _PROOF_ERROR, 401) from exc
        setattr(request.state, _PROOF_ATTR, result)
        return result

    # --- autenticacion de la peticion ---

    @staticmethod
    def _bearer(request: Request) -> str | None:
        """Token del header `Authorization: Bearer`; None si la peticion no usa
        ese esquema; "" si viene vacio."""
        values = request.headers.getlist("authorization")
        bearers = [v for v in values if v[:7].lower() == "bearer "]
        if not bearers:
            return None
        if len(values) > 1:
            return ""
        return bearers[0][7:].strip()

    async def _authenticate_service(
        self, token: str, *, use_cache: bool = True
    ) -> LeoUser:
        principal = (
            await self.sessions.service_for(token, use_cache=use_cache)
            if token
            else None
        )
        if principal is None:
            raise LeoError(
                "not_authenticated",
                "Inicia sesión para continuar.",
                401,
                www_authenticate="Bearer",
            )
        return principal

    def _reject_service(self, request: Request) -> None:
        if self._bearer(request) is not None:
            raise LeoError(
                "user_required",
                "Esta acción es solo para personas, no para aplicaciones.",
                403,
            )

    async def _authenticate(
        self, request: Request, response: Response, *, use_cache: bool
    ) -> LeoUser:
        s = self.settings
        access = request.cookies.get(self._cookie(s.access_cookie_name))
        refresh = request.cookies.get(self._cookie(s.refresh_cookie_name))
        if not access and not refresh:
            raise _not_authenticated()
        proof = await self.proof(request)
        user = None
        if access:
            user = await self.sessions.user_for(access, proof.jkt, use_cache=use_cache)
        if user is None and refresh:
            try:
                tokens = await self.sessions.refresh(refresh, proof.jkt)
            except InvalidGrantError as exc:
                raise _session_expired() from exc
            self.set_session_cookies(response, tokens)
            user = await self.sessions.user_for(tokens.access_token, proof.jkt)
        if user is None:
            raise _session_expired()
        return user

    async def current_user(self, request: Request, response: Response) -> LeoUser:
        """Dependencia FastAPI: principal autenticado. Con `Authorization:
        Bearer` es un servicio (`user.principal_type == "service"`, sin DPoP);
        si no, un usuario (cookie + DPoP, con refresh transparente cuando el
        access expiro)."""
        bearer = self._bearer(request)
        if bearer is not None:
            principal = await self._authenticate_service(bearer)
            request.state.leo_user = principal
            return principal
        user = await self._authenticate(request, response, use_cache=True)
        request.state.leo_user = user
        return user

    async def current_person(self, request: Request, response: Response) -> LeoUser:
        """Como `current_user` pero solo personas: un Bearer de servicio da 403
        `user_required` (rutas de sesion o endpoints que no son para apps)."""
        self._reject_service(request)
        return await self.current_user(request, response)

    async def heartbeat_user(self, request: Request, response: Response) -> LeoUser:
        """Como `current_user` pero introspecciona SIN cache (desliza la
        inactividad en Leo). Solo personas."""
        self._reject_service(request)
        return await self._authenticate(request, response, use_cache=False)

    def require_action(self, tag: str) -> Any:
        """Dependencia: exige el tag `app.modulo.accion`. Sin permiso: evento de
        auditoria `denied` + 403. El tag se valida (y registra) al declararse."""
        validate_tag(tag, app_slug=self.settings.app_client_id)
        self.used_tags.add(tag)

        async def dependency(
            request: Request,
            user: Annotated[LeoUser, Depends(self.current_user)],
        ) -> LeoUser:
            if not user.can(tag):
                await self.audit.record(
                    tag,
                    "denied",
                    actor=user,
                    reason="Intento de acceso sin permiso.",
                    ip=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    request_id=request.headers.get("x-request-id"),
                )
                raise LeoError(
                    "forbidden",
                    "No tienes permiso para realizar esta acción.",
                    403,
                    {"action": tag},
                )
            return user

        return Depends(dependency)

    # --- catalogo ---

    def undeclared_tags(self) -> list[str]:
        if self.catalog is None:
            return sorted(self.used_tags)
        return self.catalog.undeclared(self.used_tags)

    def check_catalog(self) -> None:
        """`CatalogMismatchError` si algun `require_action` usa un tag no
        declarado. Llamar tras importar todos los routers (p. ej. al arrancar)."""
        missing = self.undeclared_tags()
        if missing:
            raise CatalogMismatchError(missing)

    async def sync_catalog(self, *, deactivate_missing: bool = False) -> dict[str, Any]:
        if self.catalog is None:
            raise RuntimeError("LeoAuth no tiene un Catalog declarado.")
        self.check_catalog()
        return await self.client.sync_catalog(
            self.catalog.to_payload(deactivate_missing=deactivate_missing)
        )

    def leo_router(self, prefix: str = "/auth") -> APIRouter:
        return leo_router(self, prefix=prefix)


def leo_router(auth: LeoAuth, *, prefix: str = "/auth") -> APIRouter:
    """Rutas del login BFF: `/login`, `/callback`, `/me`, `/activity`,
    `/logout`. Ninguna respuesta lleva tokens en el cuerpo."""
    router = APIRouter(prefix=prefix, tags=["leo-auth"])
    s = auth.settings

    @router.get("/login")
    async def login(request: Request, response: Response) -> dict[str, str]:
        """Inicia el flujo: devuelve `authorize_url` (el cliente navega a ella).
        Requiere la prueba DPoP: el flujo queda ligado al jkt del navegador."""
        proof = await auth.proof(request)
        flow = new_flow(jkt=proof.jkt)
        auth._set_cookie(
            response, s.flow_cookie_name, auth._flow.dumps(flow), s.flow_ttl_seconds
        )
        response.headers["Cache-Control"] = "no-store"
        return {
            "authorize_url": build_authorize_url(
                s.leo_url,
                client_id=s.app_client_id,
                redirect_uri=s.callback_url,
                flow=flow,
            )
        }

    @router.get("/callback")
    async def callback(
        request: Request,
        response: Response,
        code: Annotated[str | None, Query(max_length=512)] = None,
        state: Annotated[str | None, Query(max_length=512)] = None,
        error: Annotated[str | None, Query(max_length=128)] = None,
    ) -> dict[str, Any]:
        """Canjea el code (la pagina de retorno la llama con fetch + DPoP)."""
        proof = await auth.proof(request)
        cookie_value = request.cookies.get(auth._cookie(s.flow_cookie_name))
        invalid = LeoError(
            "invalid_state",
            "La solicitud de inicio de sesión expiró o no es válida. "
            "Inicia sesión de nuevo.",
            400,
        )
        try:
            flow = auth._flow.loads(cookie_value)
        except FlowCookieError as exc:
            raise invalid from exc
        if (
            error
            or not code
            or not state
            or not constant_time_equals(flow.state, state)
            or not constant_time_equals(flow.jkt, proof.jkt)
        ):
            raise invalid
        tokens = await auth.client.exchange_code(
            code, flow.code_verifier, s.callback_url, proof.jkt
        )
        auth.set_session_cookies(response, tokens)
        auth._delete_cookie(response, s.flow_cookie_name)
        response.headers["Cache-Control"] = "no-store"
        user = await auth.sessions.user_for(tokens.access_token, proof.jkt)
        if user is None:
            raise _session_expired()
        return user.me()

    @router.get("/me")
    async def me(
        user: Annotated[LeoUser, Depends(auth.current_person)],
    ) -> dict[str, Any]:
        """`{user, session, applications}` (nunca tokens)."""
        return user.me()

    @router.post("/activity", status_code=204)
    async def activity(request: Request, response: Response) -> Response:
        """Heartbeat (~1/min): introspeccion sin cache que desliza la inactividad."""
        await auth.heartbeat_user(request, response)
        response.status_code = 204
        return response

    @router.post("/logout", status_code=204)
    async def logout(request: Request, response: Response) -> Response:
        """Revoca la sesion SSO (todas las apps) y borra las cookies."""
        auth._reject_service(request)
        access = request.cookies.get(auth._cookie(s.access_cookie_name))
        refresh = request.cookies.get(auth._cookie(s.refresh_cookie_name))
        token = access or refresh
        if token:
            proof = await auth.proof(request)
            try:
                await auth.client.revoke(token, proof.jkt)
            except InvalidGrantError:
                pass
            auth.sessions.forget(access)
        auth.clear_session_cookies(response)
        response.status_code = 204
        return response

    return router


__all__ = ["LeoAuth", "leo_router"]
