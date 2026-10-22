"""Consultas del modulo `auth`: sesiones, tokens opacos (solo hashes) y
codigos de autorizacion."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.modules.auth.models import (
    AuthorizationCode,
    ServiceToken,
    Session,
    SessionRevokedReason,
    Token,
    TokenType,
)


async def add_session(
    session: AsyncSession,
    *,
    user_id: UUID,
    jkt: str,
    secret_hash: str,
    ip: str | None,
    user_agent: str | None,
    now: datetime,
    expires_at: datetime,
) -> Session:
    sso = Session(
        user_id=user_id,
        jkt=jkt,
        secret_hash=secret_hash,
        ip=ip,
        user_agent=user_agent,
        last_activity_at=now,
        expires_at=expires_at,
    )
    session.add(sso)
    await session.flush()
    return sso


async def add_token(
    session: AsyncSession,
    *,
    token_hash: str,
    token_type: TokenType,
    session_id: UUID,
    application_id: UUID,
    jkt: str,
    expires_at: datetime,
    family_id: UUID | None = None,
) -> Token:
    token = Token(
        token_hash=token_hash,
        token_type=token_type,
        session_id=session_id,
        application_id=application_id,
        jkt=jkt,
        expires_at=expires_at,
        family_id=family_id,
    )
    session.add(token)
    await session.flush()
    return token


async def token_by_hash(session: AsyncSession, token_hash: str) -> Token | None:
    return await session.scalar(select(Token).where(Token.token_hash == token_hash))


async def add_service_token(
    session: AsyncSession,
    *,
    token_hash: str,
    caller_application_id: UUID,
    audience_application_id: UUID,
    now: datetime,
    expires_at: datetime,
) -> ServiceToken:
    """`created_at` se fija con el mismo reloj que `expires_at`: la restriccion
    `expires_at <= created_at + 1 h` de la BD se evalua sobre ambos."""
    token = ServiceToken(
        token_hash=token_hash,
        caller_application_id=caller_application_id,
        audience_application_id=audience_application_id,
        created_at=now,
        expires_at=expires_at,
    )
    session.add(token)
    await session.flush()
    return token


async def service_token_by_hash(
    session: AsyncSession, token_hash: str
) -> ServiceToken | None:
    return await session.scalar(
        select(ServiceToken)
        .where(ServiceToken.token_hash == token_hash)
        .execution_options(populate_existing=True)
    )


async def revoke_service_tokens(
    session: AsyncSession, caller_id: UUID, audience_id: UUID, now: datetime
) -> None:
    """Revoca los tokens de servicio vigentes de la llamadora para la audiencia."""
    await session.execute(
        update(ServiceToken)
        .where(
            ServiceToken.caller_application_id == caller_id,
            ServiceToken.audience_application_id == audience_id,
            ServiceToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
        .execution_options(synchronize_session="fetch")
    )


async def get_session(session: AsyncSession, session_id: UUID) -> Session | None:
    return await session.get(Session, session_id)


async def session_by_secret_hash(
    session: AsyncSession, secret_hash: str
) -> Session | None:
    """Sesion SSO por el SHA-256 del secreto de su cookie."""
    return await session.scalar(
        select(Session).where(Session.secret_hash == secret_hash)
    )


async def mark_refresh_used(
    session: AsyncSession, token_id: UUID, now: datetime
) -> bool:
    """Marca el refresh como usado solo si nadie lo uso antes (atomico)."""
    result = await session.execute(
        update(Token)
        .where(Token.id == token_id, Token.used_at.is_(None))
        .values(used_at=now)
        .returning(Token.id)
    )
    return result.scalar_one_or_none() is not None


async def revoke_session(
    session: AsyncSession, session_id: UUID, reason: SessionRevokedReason, now: datetime
) -> bool:
    """Revoca la sesion y todos sus tokens. False si ya estaba revocada."""
    result = await session.execute(
        update(Session)
        .where(Session.id == session_id, Session.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason)
        .returning(Session.id)
        .execution_options(synchronize_session="fetch")
    )
    revoked = result.scalar_one_or_none() is not None
    await session.execute(
        update(Token)
        .where(Token.session_id == session_id, Token.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session="fetch")
    )
    return revoked


async def revoke_family(session: AsyncSession, family_id: UUID, now: datetime) -> None:
    await session.execute(
        update(Token)
        .where(Token.family_id == family_id, Token.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session="fetch")
    )


async def active_session_ids_of_user(
    session: AsyncSession, user_id: UUID, except_id: UUID | None = None
) -> list[UUID]:
    stmt = select(Session.id).where(
        Session.user_id == user_id, Session.revoked_at.is_(None)
    )
    if except_id is not None:
        stmt = stmt.where(Session.id != except_id)
    return list(await session.scalars(stmt))


async def touch(session: AsyncSession, sso: Session, now: datetime) -> None:
    """Desliza la ventana de inactividad (solo hacia adelante)."""
    if now > sso.last_activity_at:
        sso.last_activity_at = now
        await session.flush()


async def add_code(
    session: AsyncSession,
    *,
    code_hash: str,
    application_id: UUID,
    session_id: UUID,
    redirect_uri: str,
    code_challenge: str,
    dpop_jkt: str,
) -> AuthorizationCode:
    code = AuthorizationCode(
        code_hash=code_hash,
        application_id=application_id,
        session_id=session_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        dpop_jkt=dpop_jkt,
    )
    session.add(code)
    await session.flush()
    return code


async def redeem_code(
    session: AsyncSession, code_hash: str
) -> AuthorizationCode | None:
    """Canje atomico: solo una peticion puede marcar el code como usado, y
    solo si no expiro (reloj de la BD)."""
    result = await session.execute(
        update(AuthorizationCode)
        .where(
            AuthorizationCode.code_hash == code_hash,
            AuthorizationCode.used_at.is_(None),
            AuthorizationCode.expires_at > func.now(),
        )
        .values(used_at=func.now())
        .returning(AuthorizationCode)
        .execution_options(synchronize_session=False)
    )
    return result.scalar_one_or_none()


async def used_code_by_hash(
    session: AsyncSession, code_hash: str
) -> AuthorizationCode | None:
    """El code si ya fue canjeado (para detectar su reuso)."""
    return await session.scalar(
        select(AuthorizationCode).where(
            AuthorizationCode.code_hash == code_hash,
            AuthorizationCode.used_at.is_not(None),
        )
    )


async def revoke_tokens_issued_since(
    session: AsyncSession,
    *,
    session_id: UUID,
    application_id: UUID,
    since: datetime,
    now: datetime,
) -> None:
    """Revoca los tokens (access y refresh, incluidos los rotados) que la
    sesion recibio para la app desde `since` (canje de un code). Sin un
    `tokens.authorization_code_id` es lo mas fino que permite el esquema."""
    await session.execute(
        update(Token)
        .where(
            Token.session_id == session_id,
            Token.application_id == application_id,
            Token.created_at >= since,
            Token.revoked_at.is_(None),
        )
        .values(revoked_at=now)
        .execution_options(synchronize_session="fetch")
    )


def sessions_statement(user_id: UUID, active_only: bool, now: datetime) -> Select:
    stmt = select(Session).where(Session.user_id == user_id)
    if active_only:
        stmt = stmt.where(Session.revoked_at.is_(None), Session.expires_at > now)
    return stmt
