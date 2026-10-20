"""Schemas del modulo `audit`."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    IPvAnyAddress,
    model_validator,
)

from app.core.validators import ActionTag, optional_text

Result = Literal["ok", "denied", "error"]


def _ip_to_str(value: object) -> object:
    return str(value) if isinstance(value, IPv4Address | IPv6Address) else value


IpStr = Annotated[str | None, BeforeValidator(_ip_to_str)]


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    actor_user_id: UUID | None
    actor_username: str | None
    application_id: UUID
    module: str | None
    action_tag: str
    entity_type: str | None
    entity_id: str | None
    changes: dict[str, Any] | None
    result: Result
    reason: str | None
    ip: IpStr
    user_agent: str | None
    session_id: UUID | None
    request_id: str | None


class IngestActorToken(BaseModel):
    """Actor = usuario dueno del access token (la app lo valida igual que en
    la introspeccion: token de ESTA app y atado a ese jkt)."""

    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(min_length=1, max_length=512)
    jkt: str = Field(min_length=43, max_length=43)


class AuditEventIngest(BaseModel):
    """Evento que envia el backend de una app (via `leo_sdk`). El tag debe
    ser de la app autenticada (`<slug-de-la-app>.<modulo>.<verbo>`)."""

    model_config = ConfigDict(extra="forbid")

    action_tag: ActionTag
    result: Result = "ok"
    actor: IngestActorToken | None = Field(
        default=None, description="Usuario por su access token (preferido)."
    )
    actor_user_id: UUID | None = Field(
        default=None,
        description="Usuario explícito (alternativa a `actor`); debe existir y "
        "tener acceso a la app.",
    )
    entity_type: optional_text(64) = None
    entity_id: optional_text(64) = None
    changes: dict[str, Any] | None = Field(
        default=None,
        description="`{campo: {before, after}}`. Los campos con nombre sensible "
        "(password, secret, token, hash...) se descartan.",
    )
    reason: optional_text(2000) = None
    ip: IPvAnyAddress | None = Field(default=None, description="IP del usuario final.")
    user_agent: optional_text(512) = None
    request_id: optional_text(64) = None

    @model_validator(mode="after")
    def _one_actor(self) -> "AuditEventIngest":
        if self.actor is not None and self.actor_user_id is not None:
            raise ValueError("Envía `actor` o `actor_user_id`, no ambos.")
        return self


class AuditEventIngested(BaseModel):
    id: UUID
