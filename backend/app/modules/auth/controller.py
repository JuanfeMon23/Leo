"""Casos de uso de `auth`: Leo como servidor de autorizacion (OAuth 2.1
code + PKCE S256 + DPoP, tokens opacos) y como BFF de su propio frontend
(sesion SSO en cookie HttpOnly atada al jkt).

Reglas de seguridad implementadas aqui:
- Login: rate limit por IP y por usuario; bloqueo tras N fallos; mensaje
  unico para usuario/contrasena incorrectos; tiempo similar exista o no.
- Sesion SSO: cookie opaca (256 bits; en BD solo su SHA-256, en
  `sessions.secret_hash`; no es una fila de `tokens`) + DPoP con el jkt de
  la sesion.
- Inactividad: si `now - last_activity_at > LEO_IDLE_TIMEOUT_MINUTES` la
  sesion se revoca (`idle-timeout`) y se rechaza; si no, se desliza.
- Code: un solo uso (canje atomico), 60 s, ligado a client, redirect_uri,
  PKCE y dpop_jkt. Si falla una verificacion, el code ya quedo quemado. Si
  un code ya canjeado vuelve a llegar, se revocan los tokens que la sesion
  recibio para esa app desde el canje (RFC 6749 4.1.2).
- Refresh rotativo: cada uso emite uno nuevo de la misma familia; presentar
  uno ya usado revoca la familia y la sesion (`refresh-reuse`).
- Introspeccion: solo tokens de la app que pregunta y con su jkt; permisos
  calculados en vivo (desactivar usuario/app/rol/accion aplica de inmediato).
- Tokens de servicio (client credentials): una app llamadora recibe un token
  opaco para UNA app destino (audiencia) si Leo le concedio >= 1 rol activo
  de ella. NO van atados a un dispositivo (no hay navegador, asi que no hay
  DPoP/jkt): por eso viven poco (10 min por defecto, tope 1 h), sin refresh,
  en la BD solo su hash, y en produccion deben viajar por red privada. Solo
  la audiencia puede introspeccionarlos; los permisos se calculan en vivo.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.audit import Actor, AuditEntry, diff
from app.core.authz import Principal
from app.core.client_auth import ClientApp
from app.core.config import get_settings
from app.core.crypto import (
    constant_time_equals,
    new_opaque_token,
    pkce_s256_matches,
    sha256_hex,
)
from app.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    TooManyRequestsError,
    UnauthorizedError,
    ValidationAppError,
    not_found,
)
from app.core.pagination import Pagination, paginate
from app.core.rate_limit import SlidingWindowLimiter
from app.core.request_meta import RequestMeta
from app.core.schemas import Page
from app.core.service_authz import ServicePrincipal
from app.modules import applications, audit, roles, users
from app.modules.auth import repository
from app.modules.auth.models import (
    AuthorizationCode,
    ServiceToken,
    Session,
    SessionRevokedReason,
    Token,
    TokenType,
)
from app.modules.auth.schemas import (
    AuthorizationCodeGrant,
    AuthorizeRequest,
    ClientCredentialsGrant,
    IntrospectClient,
    IntrospectResponse,
    IntrospectUser,
    MeApplication,
    MeResponse,
    MeSession,
    MeUser,
    PasswordChange,
    RefreshTokenGrant,
    ServiceTokenResponse,
    SessionRead,
    TokenResponse,
)

INVALID_CREDENTIALS = "Usuario o contraseña incorrectos."
TOO_MANY_ATTEMPTS = (
    "Demasiados intentos de inicio de sesión. Intenta de nuevo más tarde."
)
TOO_MANY_PASSWORD_ATTEMPTS = (
    "Demasiados intentos de cambio de contraseña. Intenta de nuevo más tarde."
)
SESSION_EXPIRED = "Tu sesión expiró. Inicia sesión de nuevo."
IDLE_EXPIRED = "Tu sesión se cerró por inactividad. Inicia sesión de nuevo."
INVALID_GRANT = (
    "La autorización no es válida, ya se usó o expiró. Inicia sesión de nuevo."
)


# --- limitadores del login (en memoria del proceso; ver core.rate_limit) ---


@dataclass
class LoginLimiters:
    by_ip: SlidingWindowLimiter
    by_login: SlidingWindowLimiter
    # Fallos de logins que NO existen: imitan el bloqueo de los que si
    # existen, para no revelar cuales existen.
    unknown_failures: SlidingWindowLimiter
    # Cambio de contrasena propio (sesion ya autenticada): intentos por IP y
    # por usuario, y contrasenas actuales incorrectas por usuario.
    password_by_ip: SlidingWindowLimiter
    password_by_user: SlidingWindowLimiter
    password_failures: SlidingWindowLimiter

    def reset(self) -> None:
        for limiter in (
            self.by_ip,
            self.by_login,
            self.unknown_failures,
            self.password_by_ip,
            self.password_by_user,
            self.password_failures,
        ):
            limiter.reset()


_limiters: LoginLimiters | None = None


def login_limiters() -> LoginLimiters:
    global _limiters
    if _limiters is None:
        s = get_settings()
        _limiters = LoginLimiters(
            by_ip=SlidingWindowLimiter(s.leo_login_rate_limit_per_minute, 60),
            by_login=SlidingWindowLimiter(s.leo_login_rate_limit_per_minute, 60),
            unknown_failures=SlidingWindowLimiter(
                s.leo_login_max_failed_attempts, s.leo_login_lock_minutes * 60
            ),
            password_by_ip=SlidingWindowLimiter(s.leo_login_rate_limit_per_minute, 60),
            password_by_user=SlidingWindowLimiter(
                s.leo_login_rate_limit_per_minute, 60
            ),
            password_failures=SlidingWindowLimiter(
                s.leo_login_max_failed_attempts, s.leo_login_lock_minutes * 60
            ),
        )
    return _limiters


_service_limiter: SlidingWindowLimiter | None = None


def service_token_limiter() -> SlidingWindowLimiter:
    """Emisiones de tokens de servicio por minuto y por cliente (en memoria)."""
    global _service_limiter
    if _service_limiter is None:
        _service_limiter = SlidingWindowLimiter(
            get_settings().leo_service_token_rate_limit_per_minute, 60
        )
    return _service_limiter


# --- resultados ---


@dataclass(frozen=True)
class LoginResult:
    me: MeResponse
    cookie_value: str
    cookie_max_age: int


@dataclass(frozen=True)
class TokenOwner:
    """Dueno de un access token valido (para introspeccion e ingesta)."""

    user_id: UUID
    username: str
    session_id: UUID
    token: Token
    first_name: str
    last_name: str
    email: str
    last_activity_at: datetime  # ya deslizada si se resolvio con touch


def _idle(now: datetime, sso: Session) -> bool:
    limit = timedelta(minutes=get_settings().leo_idle_timeout_minutes)
    return now - sso.last_activity_at > limit


def _idle_seconds() -> int:
    return get_settings().leo_idle_timeout_minutes * 60


async def _live_session(
    session: AsyncSession,
    session_id: UUID,
    now: datetime,
    meta: RequestMeta | None = None,
) -> Session | None:
    """La sesion si sigue viva (no revocada, no expirada, no inactiva). Si
    vencio por inactividad la revoca (`idle-timeout`) y lo audita, sin
    commit: quien llama confirma antes de rechazar."""
    sso = await repository.get_session(session, session_id)
    if sso is None or sso.revoked_at is not None or sso.expires_at <= now:
        return None
    if _idle(now, sso):
        await repository.revoke_session(
            session, sso.id, SessionRevokedReason.IDLE_TIMEOUT, now
        )
        await audit.record_event(
            session,
            AuditEntry(
                action_tag="leo.auth.idle-timeout",
                actor_user_id=sso.user_id,
                entity_type="session",
                entity_id=str(sso.id),
                session_id=sso.id,
                reason="Sesión revocada por inactividad.",
                ip=meta.ip if meta else None,
                user_agent=meta.user_agent if meta else None,
                request_id=meta.request_id if meta else None,
            ),
        )
        return None
    return sso


# --- login / sesion SSO (BFF de Leo) ---


async def login(
    session: AsyncSession, login_name: str, password: str, jkt: str, meta: RequestMeta
) -> LoginResult:
    settings = get_settings()
    limiters = login_limiters()
    login_key = login_name.strip().lower()
    ip_key = meta.ip or "desconocida"
    now = clock.now()

    wait = max(
        limiters.by_ip.retry_after(ip_key, now),
        limiters.by_login.retry_after(login_key, now),
    )
    if wait:
        raise TooManyRequestsError(TOO_MANY_ATTEMPTS, wait)
    limiters.by_ip.hit(ip_key, now)
    limiters.by_login.hit(login_key, now)

    wait = limiters.unknown_failures.retry_after(login_key, now)
    if wait:
        raise TooManyRequestsError(TOO_MANY_ATTEMPTS, wait)

    check = await users.check_credentials(
        session,
        login_name,
        password,
        max_failed_attempts=settings.leo_login_max_failed_attempts,
        lock_minutes=settings.leo_login_lock_minutes,
    )
    base = AuditEntry(
        action_tag="leo.auth.login",
        actor_user_id=check.user.id if check.user else None,
        actor_username=check.user.username if check.user else None,
        entity_type="user",
        entity_id=str(check.user.id) if check.user else None,
        ip=meta.ip,
        user_agent=meta.user_agent,
        request_id=meta.request_id,
    )
    outcome = check.outcome
    if outcome == users.LoginOutcome.INVALID:
        if check.user is None:
            limiters.unknown_failures.hit(login_key, now)
        base.result, base.reason = "denied", "Credenciales incorrectas."
        await audit.record_and_commit(session, base)
        raise UnauthorizedError(INVALID_CREDENTIALS, code="invalid_credentials")
    if outcome == users.LoginOutcome.LOCKED:
        if check.just_locked:
            base.action_tag, base.result = "leo.auth.lock", "denied"
            base.reason = "Usuario bloqueado por intentos fallidos."
        else:
            base.result, base.reason = "denied", "Intento con el usuario bloqueado."
        await audit.record_and_commit(session, base)
        wait = (
            int((check.locked_until - now).total_seconds())
            if check.locked_until
            else 60
        )
        raise TooManyRequestsError(TOO_MANY_ATTEMPTS, wait)
    if outcome == users.LoginOutcome.INACTIVE:
        base.result, base.reason = "denied", "Usuario desactivado."
        await audit.record_and_commit(session, base)
        raise ForbiddenError(
            "Tu usuario está desactivado. Contacta al administrador.",
            code="user_inactive",
        )

    user = check.user
    assert user is not None
    expires_at = now + timedelta(hours=settings.leo_session_max_hours)
    cookie = new_opaque_token()
    sso = await repository.add_session(
        session,
        user_id=user.id,
        jkt=jkt,
        secret_hash=cookie.hash,
        ip=meta.ip,
        user_agent=meta.user_agent,
        now=now,
        expires_at=expires_at,
    )
    leo_app_id = await applications.leo_application_id(session)
    base.session_id, base.entity_type, base.entity_id = sso.id, "session", str(sso.id)
    await audit.record_event(session, base)
    await session.commit()
    principal = Principal(
        user_id=user.id,
        username=user.username,
        session_id=sso.id,
        permissions=await roles.effective_permissions(session, user.id, leo_app_id),
    )
    return LoginResult(
        me=await me(session, principal),
        cookie_value=cookie.value,
        cookie_max_age=int((expires_at - now).total_seconds()),
    )


async def authenticate_sso(
    session: AsyncSession, cookie_value: str, jkt: str, meta: RequestMeta
) -> Principal:
    """Resuelve la cookie SSO + jkt de la prueba DPoP a un `Principal`; desliza
    la inactividad. 401 si algo no cuadra."""
    now = clock.now()
    found = await repository.session_by_secret_hash(session, sha256_hex(cookie_value))
    if found is None or found.revoked_at is not None or found.expires_at <= now:
        raise UnauthorizedError(SESSION_EXPIRED, code="session_expired")
    if not constant_time_equals(found.jkt, jkt):
        raise UnauthorizedError(
            "La prueba de posesión (DPoP) no corresponde a esta sesión.",
            code="invalid_dpop_proof",
            www_authenticate='DPoP error="invalid_dpop_proof", algs="ES256"',
        )
    sso = await _live_session(session, found.id, now, meta)
    if sso is None:
        await session.commit()
        raise UnauthorizedError(IDLE_EXPIRED, code="session_expired")
    identity = await users.get_identity(session, sso.user_id)
    if identity is None or not identity.is_active:
        raise UnauthorizedError(SESSION_EXPIRED, code="session_expired")
    await repository.touch(session, sso, now)
    await session.commit()
    leo_app_id = await applications.leo_application_id(session)
    return Principal(
        user_id=identity.id,
        username=identity.username,
        session_id=sso.id,
        permissions=await roles.effective_permissions(session, identity.id, leo_app_id),
    )


async def me(session: AsyncSession, principal: Principal) -> MeResponse:
    identity = await users.get_identity(session, principal.user_id)
    sso = await repository.get_session(session, principal.session_id)
    assert identity is not None and sso is not None
    apps = await roles.accessible_applications(session, principal.user_id)
    return MeResponse(
        user=MeUser(
            id=identity.id,
            username=identity.username,
            name=identity.full_name,
            email=identity.email,
            first_name=identity.first_name,
            last_name=identity.last_name,
        ),
        session=MeSession(
            id=sso.id,
            expires_at=sso.expires_at,
            last_activity_at=sso.last_activity_at,
            idle_timeout_seconds=_idle_seconds(),
        ),
        permissions=sorted(principal.permissions),
        applications=[
            MeApplication(slug=a.slug, name=a.name, base_url=a.base_url) for a in apps
        ],
    )


# --- autogestion: perfil y contrasena propios (solo sesion SSO, sin `leo.*`) ---


def _self_actor(principal: Principal, meta: RequestMeta) -> Actor:
    return Actor(principal.user_id, principal.username, principal.session_id, meta)


async def update_profile(
    session: AsyncSession,
    principal: Principal,
    data: users.ProfileUpdate,
    meta: RequestMeta,
) -> MeResponse:
    """Edita nombres/correo del usuario de la sesion (nunca otro: no hay id
    en la ruta). Devuelve el `MeResponse` actualizado."""
    if await users.update_own_profile(
        session, principal.user_id, data, _self_actor(principal, meta)
    ):
        await session.commit()
    return await me(session, principal)


async def change_password(
    session: AsyncSession,
    principal: Principal,
    data: PasswordChange,
    meta: RequestMeta,
) -> None:
    """Cambia la contrasena propia y cierra TODAS las otras sesiones del
    usuario (motivo `password-change`); la actual se mantiene. Rate limit por
    IP y por usuario, y bloqueo por contrasenas actuales incorrectas."""
    limiters = login_limiters()
    now = clock.now()
    user_key, ip_key = str(principal.user_id), meta.ip or "desconocida"
    wait = max(
        limiters.password_by_ip.retry_after(ip_key, now),
        limiters.password_by_user.retry_after(user_key, now),
        limiters.password_failures.retry_after(user_key, now),
    )
    if wait:
        raise TooManyRequestsError(TOO_MANY_PASSWORD_ATTEMPTS, wait)
    limiters.password_by_ip.hit(ip_key, now)
    limiters.password_by_user.hit(user_key, now)

    actor = _self_actor(principal, meta)
    try:
        await users.change_own_password(
            session, principal.user_id, data.current_password, data.new_password, actor
        )
    except UnauthorizedError:
        limiters.password_failures.hit(user_key, now)
        await audit.record_and_commit(
            session,
            actor.entry(
                "leo.users.reset-password",
                result="denied",
                entity_type="user",
                entity_id=str(principal.user_id),
                reason="autogestión: contraseña actual incorrecta.",
            ),
        )
        raise
    limiters.password_failures.reset(user_key)
    await revoke_user_sessions(
        session,
        principal.user_id,
        SessionRevokedReason.PASSWORD_CHANGE,
        except_session_id=principal.session_id,
    )
    await session.commit()


async def logout(
    session: AsyncSession, principal: Principal, meta: RequestMeta
) -> None:
    await repository.revoke_session(
        session, principal.session_id, SessionRevokedReason.LOGOUT, clock.now()
    )
    actor = Actor(principal.user_id, principal.username, principal.session_id, meta)
    await audit.record_event(
        session,
        actor.entry(
            "leo.auth.logout",
            entity_type="session",
            entity_id=str(principal.session_id),
        ),
    )
    await session.commit()


async def list_sessions(
    session: AsyncSession,
    principal: Principal,
    user_id: UUID | None,
    active_only: bool,
    pagination: Pagination,
) -> Page[SessionRead]:
    stmt = repository.sessions_statement(
        user_id or principal.user_id, active_only, clock.now()
    )
    page = await paginate(
        session, stmt, pagination, SessionRead, Session.created_at.desc()
    )
    for item in page.items:
        item.is_current = item.id == principal.session_id
    return page


async def revoke_session_by_admin(
    session: AsyncSession, session_id: UUID, actor: Actor
) -> None:
    sso = await repository.get_session(session, session_id)
    if sso is None:
        raise not_found("una sesión", session_id)
    if await repository.revoke_session(
        session, sso.id, SessionRevokedReason.ADMIN, clock.now()
    ):
        await audit.record_event(
            session,
            actor.entry(
                "leo.auth.revoke",
                entity_type="session",
                entity_id=str(sso.id),
                changes={"revoked_reason": {"before": None, "after": "admin"}},
                reason="Sesión revocada por un administrador.",
            ),
        )
    await session.commit()


async def revoke_user_sessions(
    session: AsyncSession,
    user_id: UUID,
    reason: str,
    *,
    except_session_id: UUID | None = None,
) -> None:
    """Revoca todas las sesiones (y sus tokens) de un usuario, salvo
    `except_session_id` si se da. Sin commit."""
    now = clock.now()
    for session_id in await repository.active_session_ids_of_user(
        session, user_id, except_session_id
    ):
        await repository.revoke_session(
            session, session_id, SessionRevokedReason(reason), now
        )


# --- authorize (pantalla del frontend de Leo, con la sesion SSO) ---


async def authorize(
    session: AsyncSession,
    principal: Principal,
    data: AuthorizeRequest,
    meta: RequestMeta,
) -> str:
    client = await applications.get_client_info(session, data.client_id)
    if client is None or not client.is_active:
        raise BadRequestError(
            "La aplicación que pidió el inicio de sesión no existe o está desactivada.",
            {"client_id": data.client_id},
            code="invalid_client",
        )
    if data.redirect_uri not in client.redirect_uris:
        raise BadRequestError(
            "La dirección de retorno no está registrada para esta aplicación.",
            {"redirect_uri": data.redirect_uri},
            code="invalid_redirect_uri",
        )
    actor = Actor(principal.user_id, principal.username, principal.session_id, meta)
    if not await roles.has_access(session, principal.user_id, client.id):
        await audit.record_and_commit(
            session,
            actor.entry(
                "leo.auth.authorize",
                result="denied",
                entity_type="application",
                entity_id=str(client.id),
                reason=f"Sin acceso a la aplicación «{client.slug}».",
            ),
        )
        raise ForbiddenError(
            f"No tienes acceso a «{client.name}». Pide a un administrador que te "
            "asigne un rol en esa aplicación.",
            {"client_id": client.client_id},
            code="access_denied",
        )
    code = new_opaque_token()
    await repository.add_code(
        session,
        code_hash=code.hash,
        application_id=client.id,
        session_id=principal.session_id,
        redirect_uri=data.redirect_uri,
        code_challenge=data.code_challenge,
        dpop_jkt=data.dpop_jkt,
    )
    await audit.record_event(
        session,
        actor.entry(
            "leo.auth.authorize", entity_type="application", entity_id=str(client.id)
        ),
    )
    await session.commit()
    separator = "&" if "?" in data.redirect_uri else "?"
    return f"{data.redirect_uri}{separator}{urlencode({'code': code.value, 'state': data.state})}"


# --- token (backend de la app, client credentials) ---


def _invalid_grant() -> BadRequestError:
    return BadRequestError(INVALID_GRANT, code="invalid_grant")


async def _grant_denied(
    session: AsyncSession, client: ClientApp, reason: str, sso_id: UUID | None = None
) -> BadRequestError:
    await audit.record_and_commit(
        session,
        AuditEntry(
            action_tag="leo.auth.token",
            result="denied",
            entity_type="application",
            entity_id=str(client.id),
            session_id=sso_id,
            reason=reason,
        ),
    )
    return _invalid_grant()


async def _checked_session_for_client(
    session: AsyncSession, client: ClientApp, session_id: UUID, now: datetime
) -> tuple[Session, "users.UserIdentity"] | None:
    """Sesion viva + usuario activo + acceso vigente a la app del cliente."""
    sso = await _live_session(session, session_id, now)
    if sso is None:
        return None
    identity = await users.get_identity(session, sso.user_id)
    if identity is None or not identity.is_active:
        return None
    if not await roles.has_access(session, identity.id, client.id):
        return None
    return sso, identity


async def _issue_tokens(
    session: AsyncSession,
    client: ClientApp,
    sso: Session,
    jkt: str,
    now: datetime,
    family_id: UUID | None,
) -> tuple[TokenResponse, Token]:
    access_minutes = get_settings().leo_access_token_minutes
    access_exp = min(now + timedelta(minutes=access_minutes), sso.expires_at)
    access, refresh = new_opaque_token(), new_opaque_token()
    await repository.add_token(
        session,
        token_hash=access.hash,
        token_type=TokenType.ACCESS,
        session_id=sso.id,
        application_id=client.id,
        jkt=jkt,
        expires_at=access_exp,
    )
    refresh_row = await repository.add_token(
        session,
        token_hash=refresh.hash,
        token_type=TokenType.REFRESH,
        session_id=sso.id,
        application_id=client.id,
        jkt=jkt,
        expires_at=sso.expires_at,
        family_id=family_id or uuid4(),  # canje de code = familia nueva
    )
    response = TokenResponse(
        access_token=access.value,
        refresh_token=refresh.value,
        expires_in=int((access_exp - now).total_seconds()),
        refresh_expires_in=int((sso.expires_at - now).total_seconds()),
        session_id=sso.id,
    )
    return response, refresh_row


async def exchange_code(
    session: AsyncSession, client: ClientApp, data: AuthorizationCodeGrant
) -> TokenResponse:
    now = clock.now()
    code_hash = sha256_hex(data.code)
    code = await repository.redeem_code(session, code_hash)
    await session.commit()  # el code queda quemado aunque falle lo demas
    if code is None:
        used = await repository.used_code_by_hash(session, code_hash)
        if used is not None:
            await _code_reuse_detected(session, client, used, now)
            raise _invalid_grant()
        raise await _grant_denied(session, client, "Code inexistente o expirado.")
    if code.application_id != client.id:
        raise await _grant_denied(session, client, "Code emitido para otra aplicación.")
    if code.redirect_uri != data.redirect_uri:
        raise await _grant_denied(
            session, client, "redirect_uri distinta.", code.session_id
        )
    if not pkce_s256_matches(data.code_verifier, code.code_challenge):
        raise await _grant_denied(session, client, "PKCE inválido.", code.session_id)
    if not constant_time_equals(code.dpop_jkt, data.jkt):
        raise await _grant_denied(
            session, client, "jkt distinto del code.", code.session_id
        )
    checked = await _checked_session_for_client(session, client, code.session_id, now)
    if checked is None:
        raise await _grant_denied(
            session, client, "Sesión no vigente o sin acceso.", code.session_id
        )
    sso, identity = checked
    response, _ = await _issue_tokens(session, client, sso, data.jkt, now, None)
    await repository.touch(session, sso, now)
    await audit.record_event(
        session,
        AuditEntry(
            action_tag="leo.auth.token",
            actor_user_id=identity.id,
            actor_username=identity.username,
            entity_type="application",
            entity_id=str(client.id),
            session_id=sso.id,
            reason="Canje de authorization code.",
        ),
    )
    await session.commit()
    return response


async def _code_reuse_detected(
    session: AsyncSession, client: ClientApp, code: AuthorizationCode, now: datetime
) -> None:
    """Un code ya canjeado volvio a llegar: se filtro. Se revocan los tokens
    que la sesion recibio para la app del code desde su canje (los de ese
    code y sus rotaciones), lo presente quien lo presente."""
    assert code.used_at is not None
    await repository.revoke_tokens_issued_since(
        session,
        session_id=code.session_id,
        application_id=code.application_id,
        since=code.used_at,
        now=now,
    )
    await audit.record_and_commit(
        session,
        AuditEntry(
            action_tag="leo.auth.token",
            result="denied",
            entity_type="application",
            entity_id=str(code.application_id),
            session_id=code.session_id,
            reason="Reúso de authorization code (presentado por "
            f"«{client.client_id}»): se revocaron los tokens emitidos con él.",
        ),
    )


async def refresh(
    session: AsyncSession, client: ClientApp, data: RefreshTokenGrant
) -> TokenResponse:
    now = clock.now()
    token = await repository.token_by_hash(session, sha256_hex(data.refresh_token))
    if (
        token is None
        or token.token_type != TokenType.REFRESH
        or token.application_id != client.id
    ):
        raise await _grant_denied(
            session, client, "Refresh inexistente o de otra aplicación."
        )
    if token.used_at is not None:
        await _reuse_detected(session, client, token, now)
        raise _invalid_grant()
    if token.revoked_at is not None or token.expires_at <= now:
        raise await _grant_denied(
            session, client, "Refresh revocado o expirado.", token.session_id
        )
    if not constant_time_equals(token.jkt, data.jkt):
        raise await _grant_denied(
            session, client, "jkt distinto del refresh.", token.session_id
        )
    checked = await _checked_session_for_client(session, client, token.session_id, now)
    if checked is None:
        raise await _grant_denied(
            session, client, "Sesión no vigente o sin acceso.", token.session_id
        )
    sso, _ = checked
    if not await repository.mark_refresh_used(session, token.id, now):
        await _reuse_detected(session, client, token, now)
        raise _invalid_grant()
    response, new_refresh = await _issue_tokens(
        session, client, sso, data.jkt, now, token.family_id
    )
    token.replaced_by_id = new_refresh.id
    await repository.touch(session, sso, now)
    await session.commit()
    return response


async def _reuse_detected(
    session: AsyncSession, client: ClientApp, token: Token, now: datetime
) -> None:
    """Un refresh ya usado volvio a llegar: alguien tiene una copia. Se
    revoca toda la familia y la sesion."""
    if token.family_id is not None:
        await repository.revoke_family(session, token.family_id, now)
    await repository.revoke_session(
        session, token.session_id, SessionRevokedReason.REFRESH_REUSE, now
    )
    await audit.record_and_commit(
        session,
        AuditEntry(
            action_tag="leo.auth.refresh-reuse",
            result="denied",
            entity_type="session",
            entity_id=str(token.session_id),
            session_id=token.session_id,
            reason=f"Reúso de refresh token del cliente «{client.client_id}»: "
            "se revocó la familia y la sesión.",
        ),
    )


# --- token de servicio (client credentials) ---

SERVICE_TOKEN_MAX_MINUTES = 60


async def _service_denied(
    session: AsyncSession,
    client: ClientApp,
    meta: RequestMeta,
    reason: str,
    error: BadRequestError | ForbiddenError,
) -> BadRequestError | ForbiddenError:
    await audit.record_and_commit(
        session,
        AuditEntry(
            action_tag="leo.auth.service-token",
            result="denied",
            entity_type="application",
            entity_id=str(client.id),
            reason=reason,
            ip=meta.ip,
            user_agent=meta.user_agent,
            request_id=meta.request_id,
        ),
    )
    return error


async def issue_service_token(
    session: AsyncSession,
    client: ClientApp,
    data: ClientCredentialsGrant,
    meta: RequestMeta,
) -> ServiceTokenResponse:
    """Emite un token de servicio de `client` para la app `data.audience`.
    Solo con >= 1 concesion (`service_grants`) hacia ella con rol activo."""
    now = clock.now()
    limiter = service_token_limiter()
    key = str(client.id)
    wait = limiter.retry_after(key, now)
    if wait:
        raise TooManyRequestsError(
            "Demasiadas solicitudes de token de servicio. Intenta de nuevo más tarde.",
            wait,
        )
    limiter.hit(key, now)

    audience = await applications.get_client_info(session, data.audience)
    if audience is None or not audience.is_active or audience.id == client.id:
        raise await _service_denied(
            session,
            client,
            meta,
            f"Audiencia «{data.audience}» inexistente, desactivada o igual a la "
            "llamadora.",
            BadRequestError(
                "La aplicación destino no existe, está desactivada o es la misma "
                "que la que pide el token.",
                {"audience": data.audience},
                code="invalid_target",
            ),
        )
    if not await roles.has_service_access(session, client.id, audience.id):
        raise await _service_denied(
            session,
            client,
            meta,
            f"Sin acceso concedido a «{audience.slug}».",
            ForbiddenError(
                f"Esta aplicación no tiene acceso concedido a «{audience.name}». "
                "Pide a un administrador de Leo que le conceda un rol de esa "
                "aplicación.",
                {"audience": audience.slug},
                code="access_denied",
            ),
        )
    minutes = min(get_settings().leo_service_token_minutes, SERVICE_TOKEN_MAX_MINUTES)
    expires_at = now + timedelta(minutes=minutes)
    token = new_opaque_token()
    await repository.add_service_token(
        session,
        token_hash=token.hash,
        caller_application_id=client.id,
        audience_application_id=audience.id,
        now=now,
        expires_at=expires_at,
    )
    await audit.record_event(
        session,
        AuditEntry(
            action_tag="leo.auth.service-token",
            entity_type="application",
            entity_id=str(client.id),
            changes=diff(None, {"audience": audience.slug, "expires_at": expires_at}),
            reason=f"Token de servicio de «{client.client_id}» para «{audience.slug}».",
            ip=meta.ip,
            user_agent=meta.user_agent,
            request_id=meta.request_id,
        ),
    )
    await session.commit()
    return ServiceTokenResponse(
        access_token=token.value,
        expires_in=int((expires_at - now).total_seconds()),
        audience=audience.slug,
    )


# --- introspeccion / revocacion (backend de la app) ---


async def resolve_access_token(
    session: AsyncSession,
    application_id: UUID,
    token_value: str,
    jkt: str,
    *,
    touch: bool,
) -> TokenOwner | None:
    """Dueno de un access token vigente de ESA app y atado a ESE jkt, con
    sesion viva, usuario activo y acceso a la app; si no, None. Con
    `touch=True` desliza la inactividad. Sin commit."""
    now = clock.now()
    token = await repository.token_by_hash(session, sha256_hex(token_value))
    if (
        token is None
        or token.token_type != TokenType.ACCESS
        or token.application_id != application_id
        or token.revoked_at is not None
        or token.expires_at <= now
        or not constant_time_equals(token.jkt, jkt)
    ):
        return None
    sso = await _live_session(session, token.session_id, now)
    if sso is None:
        return None
    identity = await users.get_identity(session, sso.user_id)
    if identity is None or not identity.is_active:
        return None
    if not await roles.has_access(session, identity.id, application_id):
        return None
    if touch:
        await repository.touch(session, sso, now)
    return TokenOwner(
        identity.id,
        identity.username,
        sso.id,
        token,
        identity.first_name,
        identity.last_name,
        identity.email,
        sso.last_activity_at,
    )


async def introspect(
    session: AsyncSession, client: ClientApp, token_value: str, jkt: str | None
) -> IntrospectResponse:
    """Token de servicio (solo lo valida su audiencia, sin jkt) o de usuario
    (jkt obligatorio)."""
    service = await repository.service_token_by_hash(session, sha256_hex(token_value))
    if service is not None:
        return await _introspect_service(session, client, service)
    if jkt is None:
        raise ValidationAppError(
            "Faltan datos en la petición.",
            [{"field": "jkt", "message": "Es obligatorio para tokens de usuario."}],
            code="validation_error",
        )
    owner = await resolve_access_token(session, client.id, token_value, jkt, touch=True)
    await session.commit()  # actividad deslizada o revocacion por inactividad
    if owner is None:
        return IntrospectResponse(active=False)
    permissions = await roles.effective_permissions(session, owner.user_id, client.id)
    apps = await roles.accessible_applications(session, owner.user_id)
    return IntrospectResponse(
        active=True,
        principal_type="user",
        user=IntrospectUser(
            id=owner.user_id,
            username=owner.username,
            name=f"{owner.first_name} {owner.last_name}",
            first_name=owner.first_name,
            last_name=owner.last_name,
            email=owner.email,
        ),
        permissions=sorted(permissions),
        session_id=owner.session_id,
        client_id=client.client_id,
        exp=int(owner.token.expires_at.timestamp()),
        idle_timeout_seconds=_idle_seconds(),
        applications=[
            MeApplication(slug=a.slug, name=a.name, base_url=a.base_url) for a in apps
        ],
        last_activity_at=owner.last_activity_at,
    )


async def _introspect_service(
    session: AsyncSession, client: ClientApp, token: ServiceToken
) -> IntrospectResponse:
    """`client` (la app que pregunta) debe ser la audiencia del token. Inactivo
    si expiro, se revoco, alguna de las dos apps se desactivo, o la llamadora
    ya no tiene roles activos de la audiencia. Permisos en vivo."""
    inactive = IntrospectResponse(active=False)
    now = clock.now()
    if (
        token.audience_application_id != client.id
        or token.revoked_at is not None
        or token.expires_at <= now
    ):
        return inactive
    caller = await applications.get_client_info_by_id(
        session, token.caller_application_id
    )
    if caller is None or not caller.is_active:
        return inactive
    if not await roles.has_service_access(session, caller.id, client.id):
        return inactive
    permissions = await roles.service_permissions(session, caller.id, client.id)
    return IntrospectResponse(
        active=True,
        principal_type="service",
        client=IntrospectClient(client_id=caller.client_id, name=caller.name),
        permissions=sorted(permissions),
        exp=int(token.expires_at.timestamp()),
    )


async def revoke_service_tokens(
    session: AsyncSession, caller_id: UUID, audience_id: UUID, now: datetime
) -> None:
    """Revoca los tokens de servicio vigentes de la llamadora para esa
    audiencia (al retirarle su ultima concesion). Sin commit."""
    await repository.revoke_service_tokens(session, caller_id, audience_id, now)


async def revoke_from_client(
    session: AsyncSession, client: ClientApp, token_value: str, jkt: str
) -> None:
    """Logout unico desde una app: revoca la sesion SSO completa del token
    (access o refresh de ESA app con ESE jkt). Token desconocido: no hace
    nada (RFC 7009: no se revela si existia)."""
    token = await repository.token_by_hash(session, sha256_hex(token_value))
    if (
        token is None
        or token.application_id != client.id
        or not constant_time_equals(token.jkt, jkt)
    ):
        return
    sso = await repository.get_session(session, token.session_id)
    if await repository.revoke_session(
        session, token.session_id, SessionRevokedReason.LOGOUT, clock.now()
    ):
        await audit.record_event(
            session,
            AuditEntry(
                action_tag="leo.auth.logout",
                actor_user_id=sso.user_id if sso else None,
                entity_type="session",
                entity_id=str(token.session_id),
                session_id=token.session_id,
                reason=f"Cierre de sesión desde la aplicación «{client.client_id}».",
            ),
        )
    await session.commit()


async def resolve_service_principal(
    session: AsyncSession, token_value: str
) -> ServicePrincipal | None:
    """Hook de `core.service_authz`: dueno de un token de servicio vigente cuya
    audiencia es la propia Leo, con la llamadora activa y con acceso concedido
    (permisos en vivo). Si no, None. Sin commit."""
    token = await repository.service_token_by_hash(session, sha256_hex(token_value))
    if token is None or token.revoked_at is not None or token.expires_at <= clock.now():
        return None
    leo_id = await applications.leo_application_id(session)
    if token.audience_application_id != leo_id:
        return None
    caller = await applications.get_client_info_by_id(
        session, token.caller_application_id
    )
    if caller is None or not caller.is_active:
        return None
    permissions = await roles.service_permissions(session, caller.id, leo_id)
    if not permissions:
        return None
    return ServicePrincipal(caller.id, caller.client_id, permissions)
