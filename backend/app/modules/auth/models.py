"""Tablas del modulo `auth`: sesiones SSO, tokens opacos y codigos de
autorizacion. En la BD solo hay hashes SHA-256 (hex) de tokens y codigos,
nunca su valor en claro; todo va atado a un `jkt` (thumbprint DPoP).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base
from app.core.db.checks import b64url_sha256_check, sha256_hex_check
from app.core.db.mixins import Timestamps, UUIDv7PK
from app.core.db.types import str_enum

# Vida maxima de un authorization code (Arquitectura, paso 3).
AUTHORIZATION_CODE_TTL_SECONDS = 60
# Vida maxima de un token de servicio (client credentials): 1 hora.
SERVICE_TOKEN_MAX_TTL_SECONDS = 3600


class SessionRevokedReason(enum.StrEnum):
    LOGOUT = "logout"
    ADMIN = "admin"
    USER_DEACTIVATED = "user-deactivated"
    REFRESH_REUSE = "refresh-reuse"
    IDLE_TIMEOUT = "idle-timeout"
    PASSWORD_CHANGE = "password-change"


class TokenType(enum.StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class Session(UUIDv7PK, Timestamps, Base):
    """Sesion SSO de Leo, atada a la llave no exportable del dispositivo.

    `secret_hash` es el SHA-256 (hex) del secreto de la cookie SSO de Leo:
    la cookie se busca por ese hash; el secreto en claro nunca se guarda.

    `last_activity_at` es la fuente de verdad de la inactividad (30 min,
    `LEO_IDLE_TIMEOUT_MINUTES`): el backend la actualiza y la compara.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        sha256_hex_check("secret_hash"),
        b64url_sha256_check("jkt"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_reason IS NULL)",
            name="revoked_at_with_reason",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    jkt: Mapped[str] = mapped_column(String(43), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Vida absoluta maxima, independiente de la actividad.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[SessionRevokedReason | None] = mapped_column(
        str_enum(SessionRevokedReason, "revoked_reason", 32)
    )


class Token(UUIDv7PK, Timestamps, Base):
    """Token opaco (access o refresh) emitido para una app (audiencia).

    Rotacion de refresh: todos los refresh de una cadena comparten
    `family_id`; al rotar, el usado recibe `used_at` y `replaced_by_id`. Si
    llega un refresh con `used_at` ya puesto (reuso), el backend revoca toda
    la familia (`ix_tokens_family_id`) y la sesion.
    """

    __tablename__ = "tokens"
    __table_args__ = (
        sha256_hex_check("token_hash"),
        b64url_sha256_check("jkt"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint(
            "(token_type = 'refresh') = (family_id IS NOT NULL)",
            name="family_only_for_refresh",
        ),
        CheckConstraint(
            "token_type = 'refresh' OR (used_at IS NULL AND replaced_by_id IS NULL)",
            name="rotation_only_for_refresh",
        ),
        Index("ix_tokens_family_id", "family_id"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_type: Mapped[TokenType] = mapped_column(
        str_enum(TokenType, "token_type", 16), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True
    )
    jkt: Mapped[str] = mapped_column(String(43), nullable=False)
    family_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tokens.id"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceToken(UUIDv7PK, Timestamps, Base):
    """Token de maquina (client credentials) de una app llamadora para la
    audiencia `audience_application_id`. Opaco: solo su hash SHA-256 (hex).

    Sin sesion, usuario ni `jkt`: la identidad es la app llamadora. Los
    permisos salen de `service_grants` al introspeccionarlo. Vida maxima 1 h.
    """

    __tablename__ = "service_tokens"
    __table_args__ = (
        sha256_hex_check("token_hash"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint(
            f"expires_at <= created_at + interval '{SERVICE_TOKEN_MAX_TTL_SECONDS} seconds'",
            name="ttl_max_1_hour",
        ),
        Index(
            "ix_service_tokens_caller_audience",
            "caller_application_id",
            "audience_application_id",
        ),
    )

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    caller_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False
    )
    audience_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthorizationCode(UUIDv7PK, Timestamps, Base):
    """Code de un solo uso (60 s) ligado a client, redirect_uri, PKCE S256 y
    `dpop_jkt`. Canjearlo = `UPDATE ... SET used_at = now() WHERE id = :id AND
    used_at IS NULL AND expires_at > now() RETURNING ...` (atomico).
    """

    __tablename__ = "authorization_codes"
    __table_args__ = (
        sha256_hex_check("code_hash"),
        b64url_sha256_check("code_challenge"),
        b64url_sha256_check("dpop_jkt"),
        CheckConstraint("code_challenge_method = 'S256'", name="pkce_s256_only"),
        CheckConstraint(
            "expires_at > created_at AND expires_at <= created_at + "
            f"interval '{AUTHORIZATION_CODE_TTL_SECONDS} seconds'",
            name="ttl_max_60_seconds",
        ),
    )

    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(43), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(
        String(8), server_default=text("'S256'"), nullable=False
    )
    dpop_jkt: Mapped[str] = mapped_column(String(43), nullable=False)
    # Por defecto la BD fija la expiracion (mismo reloj que `created_at`).
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text(
            f"now() + interval '{AUTHORIZATION_CODE_TTL_SECONDS} seconds'"
        ),
        nullable=False,
        index=True,
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
