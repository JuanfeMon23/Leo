"""Tablas del modulo `users`: identidades del ecosistema y sus roles."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.checks import not_blank_check
from app.core.db.mixins import ActivatableMixin, Timestamps, UUIDv7PK

# Usuario en minusculas (3-64): letras, digitos y `._-` internos. Sin `@`,
# asi el login por "usuario o email" nunca es ambiguo.
USERNAME_PATTERN = r"^[a-z0-9]([a-z0-9._-]{1,62})[a-z0-9]$"
# Forma minima de email (la validacion fina la hace el backend).
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+$"
# Numero de documento normalizado: mayusculas/digitos, guiones internos.
DOCUMENT_NUMBER_PATTERN = r"^[0-9A-Z]+(-[0-9A-Z]+)*$"


# Codigo de un catalogo: mayusculas y digitos, empieza por letra.
CATALOG_CODE_PATTERN = r"^[A-Z][A-Z0-9]*$"


class DocumentType(UUIDv7PK, Timestamps, ActivatableMixin, Base):
    """Catalogo de tipos de documento. Leo es su dueno unico: Acuarius e
    Incubus lo consumen por la API de Leo, no lo copian. `code` es la clave
    estable que referencia `users.document_type`; se desactiva (`is_active`),
    no se borra. La semilla inicial vive en `core/db/seeds/catalog.py`."""

    __tablename__ = "document_types"
    __table_args__ = (
        CheckConstraint(f"code ~ '{CATALOG_CODE_PATTERN}'", name="code_format"),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
        not_blank_check("name"),
    )

    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )


class User(UUIDv7PK, Timestamps, ActivatableMixin, Base):
    """Identidad unica de una persona en todo el ecosistema."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("document_type", "document_number"),
        # Email unico sin distinguir mayusculas (la columna conserva lo escrito).
        Index("uq_users_email_lower", func.lower(text("email")), unique=True),
        CheckConstraint(f"username ~ '{USERNAME_PATTERN}'", name="username_format"),
        CheckConstraint(f"email ~ '{EMAIL_PATTERN}'", name="email_format"),
        CheckConstraint(
            f"document_number ~ '{DOCUMENT_NUMBER_PATTERN}'",
            name="document_number_format",
        ),
        CheckConstraint(
            "password_hash LIKE '$argon2id$%'", name="password_hash_argon2id"
        ),
        CheckConstraint(
            "failed_login_attempts >= 0", name="failed_login_attempts_non_negative"
        ),
        not_blank_check("first_name"),
        not_blank_check("last_name"),
    )

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    # Hash argon2id completo (PHC: algoritmo, parametros y sal).
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # FK al `code` del catalogo (el backend valida que exista y este activo).
    document_type: Mapped[str] = mapped_column(
        String(8), ForeignKey("document_types.code"), nullable=False
    )
    document_number: Mapped[str] = mapped_column(String(32), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    # Bloqueado mientras `locked_until > now()`; NULL = no bloqueado.
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserRole(UUIDv7PK, Timestamps, Base):
    """Rol asignado a un usuario. Quitarlo = borrar la fila (queda en la
    auditoria). Acceso a una app = >= 1 rol activo de esa app."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True
    )
