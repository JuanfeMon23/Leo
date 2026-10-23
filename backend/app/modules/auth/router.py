"""Rutas `/api/v1/auth`.

- Navegador (frontend de Leo, cookie SSO + header `DPoP`): `/login`,
  `/activity`, `/me`, `/logout`, `/sessions`, `/sessions/{id}/revoke`,
  `/authorize`.
- Backend de las apps (client credentials por HTTP Basic, via `leo_sdk`):
  `/token`, `/introspect`, `/revoke`.
- Servicio a servicio (client credentials, OAuth 2.0 4.4): `/token` con
  `grant_type=client_credentials` emite un token de servicio y `/introspect`
  (de la app audiencia) lo valida sin `jkt`.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.core.audit import Actor
from app.core.authz import CurrentPrincipal, require_actor
from app.core.client_auth import AuthenticatedClient
from app.core.config import get_settings
from app.core.database import SessionDep
from app.core.pagination import PaginationDep
from app.core.request_meta import Meta
from app.core.schemas import AUTH_ERRORS, Page, error_responses
from app.modules import users
from app.modules.auth import controller
from app.modules.auth.dependencies import RequestDpop, session_cookie_name
from app.modules.auth.schemas import (
    AuthorizationCodeGrant,
    AuthorizeRequest,
    AuthorizeResponse,
    ClientCredentialsGrant,
    IntrospectRequest,
    IntrospectResponse,
    LoginRequest,
    MeResponse,
    PasswordChange,
    PasswordPolicyRead,
    ServiceTokenResponse,
    SessionRead,
    TokenCheck,
    TokenRequest,
    TokenResponse,
)

router = APIRouter(tags=["auth"])

NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _set_session_cookie(response: Response, value: str, max_age: int) -> None:
    response.set_cookie(
        session_cookie_name(),
        value,
        max_age=max_age,
        path="/",
        secure=get_settings().leo_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        session_cookie_name(),
        path="/",
        secure=get_settings().leo_cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.post(
    "/login",
    response_model=MeResponse,
    responses=error_responses(401, 403, 422, 429),
    summary="Iniciar sesión SSO (usuario o email + contraseña + header DPoP)",
    description="Crea la sesión atada al jkt de la prueba DPoP y fija la cookie "
    "HttpOnly `__Host-leo_session` (o `leo_session` sin HTTPS). El cuerpo nunca "
    "lleva tokens.",
)
async def login(
    session: SessionDep,
    data: LoginRequest,
    proof: RequestDpop,
    meta: Meta,
    response: Response,
) -> MeResponse:
    result = await controller.login(session, data.login, data.password, proof.jkt, meta)
    _set_session_cookie(response, result.cookie_value, result.cookie_max_age)
    response.headers.update(NO_STORE)
    return result.me


@router.get(
    "/password-policy",
    response_model=PasswordPolicyRead,
    responses=error_responses(429),
    summary="Política de contraseñas vigente (pública, sin sesión)",
    description="Reglas actuales (ajustes `password.*`) para validar en el "
    "cliente antes de enviar; el servidor las vuelve a aplicar. Sin datos "
    "sensibles. Cacheable 30 s; limitado por IP (`rate_limit.public_policy_per_window`).",
)
async def password_policy(meta: Meta, response: Response) -> PasswordPolicyRead:
    policy = await controller.public_password_policy(meta)
    response.headers["Cache-Control"] = "public, max-age=30"
    return PasswordPolicyRead.model_validate(policy.model_dump())


@router.post(
    "/activity",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401),
    summary="Heartbeat de actividad (mouse/teclado) del frontend de Leo",
)
async def activity(_principal: CurrentPrincipal) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=MeResponse,
    responses=error_responses(401),
    summary="Usuario, permisos leo.* y apps accesibles (selector de la barra)",
)
async def me(session: SessionDep, principal: CurrentPrincipal) -> MeResponse:
    return await controller.me(session, principal)


@router.patch(
    "/me/profile",
    response_model=MeResponse,
    responses=error_responses(401, 403, 409, 422, 429),
    summary="Editar mis nombres y correo (autogestión; sin permisos `leo.*`)",
    description="Solo `first_name`, `last_name` y `email` del usuario de la "
    "sesión. Usuario, documento, estado y roles no se editan aquí (422). Sin "
    "cambios reales no escribe. Correo único sin distinguir mayúsculas (409 "
    "`duplicate`, `details.email`).\n\n"
    "**Cambiar a OTRO correo exige `current_password`** (una sesión robada no "
    "debe poder tomar la cuenta): falta -> 422 `current_password_required`; "
    "incorrecta -> 403 `invalid_current_password` (mensaje genérico, cuenta "
    "como intento fallido con el mismo bloqueo que `/me/password`, 429 "
    "`too_many_attempts`); correcta -> cambia y cierra las demás sesiones "
    "(la actual se mantiene). Solo nombres, o solo cambiar mayúsculas del "
    "mismo correo, no la piden; sin cambio de correo `current_password` se "
    "ignora.",
)
async def update_profile(
    session: SessionDep,
    data: users.ProfileUpdate,
    principal: CurrentPrincipal,
    meta: Meta,
) -> MeResponse:
    return await controller.update_profile(session, principal, data, meta)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 422, 429),
    summary="Cambiar mi contraseña (autogestión; sin permisos `leo.*`)",
    description="Exige la contraseña actual (401 `invalid_credentials`), aplica "
    "la política de contraseñas (422 `weak_password`; `same_password` si es "
    "igual a la actual) y cierra todas las demás sesiones del usuario; la "
    "actual se mantiene. 429 `too_many_attempts` con rate limit por usuario e IP.",
)
async def change_password(
    session: SessionDep, data: PasswordChange, principal: CurrentPrincipal, meta: Meta
) -> Response:
    await controller.change_password(session, principal, data, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=NO_STORE)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401),
    summary="Cerrar la sesión SSO (todas las apps)",
)
async def logout(
    session: SessionDep, principal: CurrentPrincipal, meta: Meta
) -> Response:
    await controller.logout(session, principal, meta)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response)
    return response


@router.get(
    "/sessions",
    response_model=Page[SessionRead],
    responses=error_responses(*AUTH_ERRORS),
    summary="Sesiones propias o de un usuario (`user_id`)",
)
async def list_sessions(
    session: SessionDep,
    pagination: PaginationDep,
    actor: Annotated[Actor, require_actor("leo.auth.view")],
    principal: CurrentPrincipal,
    user_id: Annotated[UUID | None, Query()] = None,
    active_only: Annotated[bool, Query()] = True,
) -> Page[SessionRead]:
    return await controller.list_sessions(
        session, principal, user_id, active_only, pagination
    )


@router.post(
    "/sessions/{session_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def revoke_session(
    session: SessionDep,
    session_id: UUID,
    actor: Annotated[Actor, require_actor("leo.auth.revoke")],
) -> Response:
    await controller.revoke_session_by_admin(session, session_id, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/authorize",
    response_model=AuthorizeResponse,
    responses=error_responses(400, 401, 403, 422),
    summary="Emitir un authorization code para una app (pantalla authorize)",
)
async def authorize(
    session: SessionDep, data: AuthorizeRequest, principal: CurrentPrincipal, meta: Meta
) -> AuthorizeResponse:
    return AuthorizeResponse(
        redirect_to=await controller.authorize(session, principal, data, meta)
    )


@router.post(
    "/token",
    response_model=TokenResponse | ServiceTokenResponse,
    responses=error_responses(400, 401, 403, 422, 429),
    summary="Canjear code (PKCE), rotar refresh o pedir un token de servicio "
    "(client credentials, HTTP Basic)",
    description="`grant_type`: `authorization_code` y `refresh_token` (usuarios, "
    "atados al `jkt` DPoP del dispositivo) o `client_credentials` (servicio a "
    "servicio): la app autenticada con Basic pide un token para la app "
    "`audience`, que Leo concede solo si tiene >= 1 rol activo de ella "
    "(`service_grants`).\n\n"
    "**Decisión de seguridad (tokens de servicio):** no van atados a un "
    "dispositivo (no hay navegador, así que no hay DPoP/`jkt`). Por eso viven "
    "poco (`LEO_SERVICE_TOKEN_MINUTES`, 10 por defecto, tope 60), no tienen "
    "refresh y en Leo solo se guarda su hash. Quien lo roba puede usarlo hasta "
    "que vence: **en producción debe viajar por red privada**. Solo la app "
    "`audience` puede validarlo (`/introspect`).",
)
async def token(
    session: SessionDep,
    data: TokenRequest,
    client: AuthenticatedClient,
    response: Response,
    meta: Meta,
) -> TokenResponse | ServiceTokenResponse:
    response.headers.update(NO_STORE)
    if isinstance(data, AuthorizationCodeGrant):
        return await controller.exchange_code(session, client, data)
    if isinstance(data, ClientCredentialsGrant):
        return await controller.issue_service_token(session, client, data, meta)
    return await controller.refresh(session, client, data)


@router.post(
    "/introspect",
    response_model=IntrospectResponse,
    response_model_exclude_none=True,
    responses=error_responses(401, 422),
    summary="Introspección de un access token (client credentials); desliza la "
    "inactividad",
    description="Token de usuario: `jkt` obligatorio; responde usuario, permisos "
    "y sesión (`principal_type: user`). Token de servicio: sin `jkt`; solo la "
    "app audiencia del token lo valida y responde `principal_type: service`, "
    "`client` (la llamadora), `permissions` y `exp`. Cualquier otro caso: "
    '`{"active": false}`.',
)
async def introspect(
    session: SessionDep,
    data: IntrospectRequest,
    client: AuthenticatedClient,
    response: Response,
) -> IntrospectResponse:
    response.headers.update(NO_STORE)
    return await controller.introspect(session, client, data.token, data.jkt)


@router.post(
    "/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 422),
    summary="Logout único desde una app: revoca la sesión SSO del token",
)
async def revoke(
    session: SessionDep, data: TokenCheck, client: AuthenticatedClient
) -> Response:
    await controller.revoke_from_client(session, client, data.token, data.jkt)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
