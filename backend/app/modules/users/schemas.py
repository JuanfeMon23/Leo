"""Schemas del modulo `users`. Nunca exponen `password_hash`."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.core.security.passwords import MAX_PASSWORD_LENGTH
from app.core.validators import UpdateModel, text
from app.modules.users.models import (
    DOCUMENT_NUMBER_PATTERN,
    EMAIL_PATTERN,
    USERNAME_PATTERN,
    DocumentType,
)


def _lower(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


def _upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


Username = Annotated[
    str,
    BeforeValidator(_lower),
    StringConstraints(min_length=3, max_length=64, pattern=USERNAME_PATTERN),
    Field(description="3-64: minúsculas, dígitos y . _ - internos (sin @)."),
]
Email = Annotated[
    str,
    BeforeValidator(_strip),
    StringConstraints(max_length=254, pattern=EMAIL_PATTERN),
]
DocumentNumber = Annotated[
    str,
    BeforeValidator(_upper),
    StringConstraints(min_length=1, max_length=32, pattern=DOCUMENT_NUMBER_PATTERN),
    Field(description="Dígitos/letras y guiones internos, sin puntos ni espacios."),
]
PersonName = text(100)
Password = Annotated[
    str, StringConstraints(min_length=1, max_length=MAX_PASSWORD_LENGTH)
]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    email: Email
    password: Password = Field(
        description="12-128 caracteres, con minúscula, mayúscula, dígito y símbolo; "
        "sin contener el usuario ni el email."
    )
    document_type: DocumentType
    document_number: DocumentNumber
    first_name: PersonName
    last_name: PersonName


class UserUpdate(UpdateModel):
    immutable_fields = ("username", "password")
    non_nullable_fields = (
        "email",
        "document_type",
        "document_number",
        "first_name",
        "last_name",
    )

    email: Email | None = None
    document_type: DocumentType | None = None
    document_number: DocumentNumber | None = None
    first_name: PersonName | None = None
    last_name: PersonName | None = None


class ProfileUpdate(UpdateModel):
    """Autogestion (`PATCH /auth/me/profile`): SOLO nombres y correo. Cualquier
    otro campo (usuario, documento, estado, roles, contrasena) lo rechaza
    `extra="forbid"`."""

    non_nullable_fields = ("email", "first_name", "last_name")

    email: Email | None = None
    first_name: PersonName | None = None
    last_name: PersonName | None = None
    current_password: str | None = Field(
        default=None,
        min_length=1,
        max_length=1024,
        description="Contraseña actual: obligatoria SOLO si `email` cambia a otro "
        "correo (anti toma de cuenta con sesión robada). Sin cambio de correo "
        "se ignora (no se verifica ni cuenta como intento).",
    )


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: Password


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    document_type: DocumentType
    document_number: str
    first_name: str
    last_name: str
    is_active: bool
    last_login_at: datetime | None
    failed_login_attempts: int
    locked_until: datetime | None
    created_at: datetime
    updated_at: datetime


class UserRoleRead(BaseModel):
    id: UUID
    application_id: UUID
    slug: str
    name: str
    is_active: bool


class UserDetail(UserRead):
    roles: list[UserRoleRead] = Field(default_factory=list)


class UserRolesAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_ids: list[UUID] = Field(min_length=1, max_length=200)


class PatientProvision(UserCreate):
    """Cuerpo de `POST /users/service/patients` (mismos campos y politica de
    contrasena que `UserCreate`; el rol `paciente` lo fija el servidor)."""


class PatientRead(BaseModel):
    """Paciente aprovisionado. Sin hash ni datos de bloqueo."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    document_type: DocumentType
    document_number: str
    first_name: str
    last_name: str
    is_active: bool
    created_at: datetime


USER_ACCESS_TOKEN_FIELD = Field(
    min_length=1,
    max_length=512,
    description="Access token que Leo emitio al usuario para la app llamadora. "
    "De el sale el usuario objetivo; nunca se acepta un id del cliente.",
)


class DelegatedProfileUpdate(ProfileUpdate):
    """Cuerpo de `PATCH /users/service/delegated/profile`: los campos de
    `ProfileUpdate` + el token del usuario."""

    user_access_token: str = USER_ACCESS_TOKEN_FIELD

    def profile(self) -> ProfileUpdate:
        """Solo los campos del perfil, conservando cuales venian informados."""
        return ProfileUpdate.model_validate(
            self.model_dump(exclude={"user_access_token"}, exclude_unset=True)
        )


class DelegatedPasswordChange(BaseModel):
    """Cuerpo de `POST /users/service/delegated/password`."""

    model_config = ConfigDict(extra="forbid")

    user_access_token: str = USER_ACCESS_TOKEN_FIELD
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class DelegatedProfileRead(BaseModel):
    """Perfil minimo devuelto tras editar en nombre del usuario."""

    first_name: str
    last_name: str
    email: str
    username: str
