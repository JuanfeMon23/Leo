"""Schemas del modulo `roles`."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.validators import Slug, UpdateModel, optional_text, text

Name = text(128)
Description = optional_text(2000)


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: UUID
    slug: Slug
    name: Name
    description: Description = None


class RoleUpdate(UpdateModel):
    immutable_fields = ("slug", "application_id")
    non_nullable_fields = ("name",)

    name: Name | None = None
    description: Description = None


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    slug: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RoleActionModule(BaseModel):
    id: UUID
    slug: str
    name: str


class RoleActionRead(BaseModel):
    """Accion asignada a un rol, con lo necesario para agruparla por modulo y
    mostrar su nombre legible."""

    id: UUID
    tag: str
    verb: str
    name: str
    description: str | None
    is_active: bool
    module: RoleActionModule


class RoleDetail(RoleRead):
    actions: list[RoleActionRead] = Field(default_factory=list)


class RoleActionsAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_ids: list[UUID] = Field(min_length=1, max_length=500)
