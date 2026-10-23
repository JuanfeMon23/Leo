"""Modelos de datos del SDK (respuestas de Leo y usuario autenticado)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TokenSet(BaseModel):
    access_token: str = Field(repr=False)
    refresh_token: str = Field(repr=False)
    token_type: str = "DPoP"
    expires_in: int
    refresh_expires_in: int
    session_id: UUID


class IntrospectUser(BaseModel):
    id: UUID
    username: str
    name: str
    email: str
    # Opcionales: Leo aun puede no enviarlos (el SDK los usa cuando lleguen).
    first_name: str | None = None
    last_name: str | None = None


class AppInfo(BaseModel):
    """App a la que el usuario tiene acceso (selector de la barra superior)."""

    slug: str
    name: str
    base_url: str


class ServiceToken(BaseModel):
    """Token de servicio (`client_credentials`): Bearer, sin refresh."""

    access_token: str = Field(repr=False)
    token_type: str = "Bearer"
    expires_in: int
    audience: str


class ServiceClient(BaseModel):
    """App llamadora de un token de servicio."""

    client_id: str
    name: str


class Introspection(BaseModel):
    active: bool
    principal_type: str | None = None  # "user" | "service" (None: Leo antiguo)
    client: ServiceClient | None = None  # solo tokens de servicio
    user: IntrospectUser | None = None
    permissions: list[str] = Field(default_factory=list)
    session_id: UUID | None = None
    client_id: str | None = None
    exp: int | None = None
    idle_timeout_seconds: int | None = None
    applications: list[AppInfo] = Field(default_factory=list)
    last_activity_at: datetime | None = None


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class LeoUser:
    """Usuario autenticado en la peticion, con sus permisos EN ESTA app.

    `access_token` y `jkt` se conservan para actuar en nombre del usuario
    (auditoria); no aparecen en `repr` ni se serializan con `public()`.
    """

    id: UUID
    username: str
    name: str
    email: str
    permissions: frozenset[str]
    session_id: UUID | None
    access_token: str = field(repr=False, default="")
    jkt: str = field(repr=False, default="")
    first_name: str = ""
    last_name: str = ""
    applications: tuple[AppInfo, ...] = ()
    expires_at: datetime | None = None
    last_activity_at: datetime | None = None
    idle_timeout_seconds: int | None = None
    # "user" (cookie + DPoP) o "service" (Bearer de client_credentials). Un
    # servicio no tiene sesion: `session_id` es None, `username` es su
    # `client_id`, `id` es un UUID derivado del `client_id` y no hay `email`.
    principal_type: str = "user"
    client_id: str | None = None

    @property
    def is_service(self) -> bool:
        return self.principal_type == "service"

    def can(self, tag: str) -> bool:
        return tag in self.permissions

    def public(self) -> dict:
        """Forma segura para el navegador (nunca tokens)."""
        return {
            "id": str(self.id),
            "username": self.username,
            "name": self.name,
            "first_name": self.first_name or self.name,
            "last_name": self.last_name,
            "email": self.email,
            "permissions": sorted(self.permissions),
            "session_id": (None if self.session_id is None else str(self.session_id)),
        }

    def me(self) -> dict:
        """Cuerpo de `/auth/me` y `/auth/callback`: `{user, session, applications}`."""
        return {
            "user": self.public(),
            "session": {
                "expires_at": _iso(self.expires_at) if self.expires_at else None,
                "last_activity_at": (
                    _iso(self.last_activity_at) if self.last_activity_at else None
                ),
                "idle_timeout_seconds": self.idle_timeout_seconds,
            },
            "applications": [a.model_dump() for a in self.applications],
        }


class UserProfile(BaseModel):
    """Perfil minimo devuelto al editar en nombre del usuario."""

    first_name: str
    last_name: str
    email: str
    username: str


class PasswordPolicy(BaseModel):
    """Politica de contrasenas de Leo (`GET /auth/password-policy`, publica).

    Es la unica implementacion de las reglas: el backend de Leo la reutiliza.
    `check` devuelve los codigos de requisitos incumplidos.
    """

    model_config = ConfigDict(frozen=True)

    min_length: int = 12
    max_length: int = 128
    require_lowercase: bool = True
    require_uppercase: bool = True
    require_digit: bool = True
    require_symbol: bool = True

    def check(self, password: str) -> list[str]:
        """Codigos incumplidos: `too_short`, `too_long`, `no_lowercase`,
        `no_uppercase`, `no_digit`, `no_symbol`; `[]` si la cumple."""
        problems = []
        if len(password) < self.min_length:
            problems.append("too_short")
        if len(password) > self.max_length:
            problems.append("too_long")
        if self.require_lowercase and not any(c.islower() for c in password):
            problems.append("no_lowercase")
        if self.require_uppercase and not any(c.isupper() for c in password):
            problems.append("no_uppercase")
        if self.require_digit and not any(c.isdigit() for c in password):
            problems.append("no_digit")
        if self.require_symbol and all(c.isalnum() for c in password):
            problems.append("no_symbol")
        return problems

    def is_valid(self, password: str) -> bool:
        return not self.check(password)
