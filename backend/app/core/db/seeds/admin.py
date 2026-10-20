"""Administrador inicial: datos SOLO desde `backend/.env` (`LEO_ADMIN_*`).

`load_seed_config` valida todo antes de escribir nada: variables faltantes
(o en blanco), tipo/numero de documento, usuario, email y fuerza de la
contrasena. Los mensajes nombran la variable, nunca muestran su valor.
"""

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import SeedSettings
from app.core.security.passwords import hash_password, password_weaknesses
from app.modules.users.models import (
    DOCUMENT_NUMBER_PATTERN,
    EMAIL_PATTERN,
    USERNAME_PATTERN,
    DocumentType,
    User,
    UserRole,
)

DEFAULT_FIRST_NAME = "Administrador"
DEFAULT_LAST_NAME = "Leo"

# Campos obligatorios de SeedSettings (variable = "LEO_" + campo en mayusculas).
REQUIRED = (
    "frontend_url",
    "admin_username",
    "admin_email",
    "admin_password",
    "admin_document_type",
    "admin_document_number",
)


class SeedConfigError(Exception):
    """Configuracion de la semilla incompleta o invalida (mensaje legible)."""


@dataclass(frozen=True)
class SeedConfig:
    frontend_url: str
    username: str
    email: str
    password: str
    document_type: DocumentType
    document_number: str
    first_name: str
    last_name: str


def _env_name(field: str) -> str:
    return f"LEO_{field.upper()}"


def _value(settings: SeedSettings, field: str) -> str | None:
    raw = getattr(settings, field)
    if raw is not None and hasattr(raw, "get_secret_value"):
        raw = raw.get_secret_value()
    return raw.strip() if raw and raw.strip() else None


def load_seed_config(settings: SeedSettings) -> SeedConfig:
    values = {field: _value(settings, field) for field in REQUIRED}
    missing = [_env_name(f) for f, v in values.items() if v is None]
    if missing:
        raise SeedConfigError(
            "Faltan variables en backend/.env para la semilla: "
            f"{', '.join(missing)}. Ver backend/.env.example."
        )

    errors = []
    username = values["admin_username"].lower()
    if not re.match(USERNAME_PATTERN, username):
        errors.append(
            "LEO_ADMIN_USERNAME no es valido (3-64 caracteres: minusculas, "
            "digitos y . _ - internos)."
        )
    email = values["admin_email"]
    if not re.match(EMAIL_PATTERN, email):
        errors.append("LEO_ADMIN_EMAIL no es un email valido.")
    document_type = values["admin_document_type"].upper()
    if document_type not in {t.value for t in DocumentType}:
        errors.append(
            "LEO_ADMIN_DOCUMENT_TYPE no es valido; usa uno de: "
            f"{', '.join(t.value for t in DocumentType)}."
        )
    document_number = values["admin_document_number"].upper()
    if not re.match(DOCUMENT_NUMBER_PATTERN, document_number):
        errors.append(
            "LEO_ADMIN_DOCUMENT_NUMBER no es valido (solo digitos/letras y "
            "guiones internos, sin puntos ni espacios)."
        )
    password = values["admin_password"]
    weaknesses = password_weaknesses(password, username=username, email=email)
    if weaknesses:
        errors.append(f"LEO_ADMIN_PASSWORD es debil: {'; '.join(weaknesses)}.")
    if errors:
        raise SeedConfigError(" ".join(errors))

    return SeedConfig(
        frontend_url=values["frontend_url"],
        username=username,
        email=email,
        password=password,
        document_type=DocumentType(document_type),
        document_number=document_number,
        first_name=_value(settings, "admin_first_name") or DEFAULT_FIRST_NAME,
        last_name=_value(settings, "admin_last_name") or DEFAULT_LAST_NAME,
    )


def seed_admin_user(conn: Connection, config: SeedConfig, role_id: UUID) -> bool:
    """Crea el admin si no existe (por username) y le asigna `role_id`.

    Si ya existe no lo toca (ni su contrasena). Devuelve True si lo creo.
    """
    users = User.__table__
    user_id = conn.scalar(select(users.c.id).where(users.c.username == config.username))
    created = user_id is None
    if created:
        user_id = conn.scalar(
            insert(users)
            .values(
                username=config.username,
                email=config.email,
                password_hash=hash_password(config.password),
                document_type=config.document_type.value,
                document_number=config.document_number,
                first_name=config.first_name,
                last_name=config.last_name,
            )
            .returning(users.c.id)
        )
    conn.execute(
        insert(UserRole.__table__)
        .values(user_id=user_id, role_id=role_id)
        .on_conflict_do_nothing(index_elements=["user_id", "role_id"])
    )
    return created
