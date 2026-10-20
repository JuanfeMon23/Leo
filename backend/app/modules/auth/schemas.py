"""Schemas del modulo `auth` (login/BFF de Leo y endpoints del protocolo).

Los tokens solo aparecen en las respuestas de `/token` (servidor a servidor,
al backend de la app); nunca en respuestas al navegador.
"""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.core.db.checks import B64URL_SHA256_PATTERN

Jkt = Annotated[
    str,
    StringConstraints(pattern=B64URL_SHA256_PATTERN),
    Field(
        description="Thumbprint RFC 7638 (base64url, 43 caracteres) de la llave DPoP."
    ),
]
OpaqueTokenStr = Annotated[str, StringConstraints(min_length=1, max_length=512)]
# RFC 7636: 43-128 caracteres no reservados.
CodeVerifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9\-._~]{43,128}$")]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=1, max_length=254, description="Usuario o email.")
    password: str = Field(min_length=1, max_length=1024)


class MeUser(BaseModel):
    id: UUID
    username: str
    email: str
    first_name: str
    last_name: str


class MeSession(BaseModel):
    id: UUID
    expires_at: datetime
    last_activity_at: datetime
    idle_timeout_seconds: int


class MeApplication(BaseModel):
    slug: str
    name: str
    base_url: str


class MeResponse(BaseModel):
    user: MeUser
    session: MeSession
    permissions: list[str] = Field(description="Tags `leo.*` efectivos (ordenados).")
    applications: list[MeApplication] = Field(
        description="Apps a las que tiene acceso (>= 1 rol activo en app activa)."
    )


def _ip(value: object) -> object:
    return str(value) if isinstance(value, IPv4Address | IPv6Address) else value


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    ip: Annotated[str | None, BeforeValidator(_ip)]
    user_agent: str | None
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revoked_reason: str | None
    is_current: bool = False


class AuthorizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(min_length=1, max_length=64)
    redirect_uri: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=512)
    code_challenge: Annotated[str, StringConstraints(pattern=B64URL_SHA256_PATTERN)]
    code_challenge_method: Literal["S256"] = "S256"
    dpop_jkt: Jkt


class AuthorizeResponse(BaseModel):
    redirect_to: str = Field(description="`redirect_uri?code=...&state=...`")


class AuthorizationCodeGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grant_type: Literal["authorization_code"]
    code: OpaqueTokenStr
    code_verifier: CodeVerifier
    redirect_uri: str = Field(min_length=1, max_length=2048)
    jkt: Jkt


class RefreshTokenGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grant_type: Literal["refresh_token"]
    refresh_token: OpaqueTokenStr
    jkt: Jkt


TokenRequest = Annotated[
    AuthorizationCodeGrant | RefreshTokenGrant, Field(discriminator="grant_type")
]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["DPoP"] = "DPoP"
    expires_in: int = Field(description="Segundos de vida del access token.")
    refresh_expires_in: int = Field(description="Segundos de vida del refresh token.")
    session_id: UUID


class TokenCheck(BaseModel):
    """Cuerpo de `/introspect` y `/revoke` (client credentials)."""

    model_config = ConfigDict(extra="forbid")

    token: OpaqueTokenStr
    jkt: Jkt


class IntrospectUser(BaseModel):
    id: UUID
    username: str
    name: str = Field(description="Nombre completo (`first_name last_name`).")
    first_name: str
    last_name: str
    email: str


class IntrospectResponse(BaseModel):
    active: bool
    user: IntrospectUser | None = None
    permissions: list[str] | None = Field(
        default=None, description="Tags efectivos del usuario en ESTA app."
    )
    session_id: UUID | None = None
    client_id: str | None = None
    exp: int | None = Field(default=None, description="Expiración del token (epoch s).")
    idle_timeout_seconds: int | None = None
    applications: list[MeApplication] | None = Field(
        default=None,
        description="Apps a las que el usuario tiene acceso (rol activo en app "
        "activa): solo slug, name y base_url.",
    )
    last_activity_at: datetime | None = Field(
        default=None,
        description="Actividad de la sesión ya deslizada por esta introspección.",
    )
