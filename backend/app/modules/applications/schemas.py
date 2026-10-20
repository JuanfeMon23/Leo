"""Schemas de entrada/salida del modulo `applications`.

Nunca exponen `client_secret_hash`; el `client_secret` en claro solo sale en
`ApplicationCreated` / `SecretRotated` (una vez).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.validators import HttpUrlStr, Slug, UpdateModel, optional_text, text

Name = text(128)
Description = optional_text(2000)
ActionName = text(120)
"""Nombre legible de una accion (1..120, sin espacios en los extremos; solo
blancos = invalido). Unico dentro del modulo."""

MAX_REDIRECT_URIS = 20


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: Name
    description: Description = None
    base_url: HttpUrlStr
    redirect_uris: list[HttpUrlStr] = Field(
        default_factory=list, max_length=MAX_REDIRECT_URIS
    )


class ApplicationUpdate(UpdateModel):
    immutable_fields = ("slug", "client_id")
    non_nullable_fields = ("name", "base_url", "redirect_uris")

    name: Name | None = None
    description: Description = None
    base_url: HttpUrlStr | None = None
    redirect_uris: list[HttpUrlStr] | None = Field(
        default=None, max_length=MAX_REDIRECT_URIS
    )


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    base_url: str
    redirect_uris: list[str]
    client_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ApplicationCreated(BaseModel):
    application: ApplicationRead
    client_secret: str = Field(
        description="Secreto del cliente en claro. Se muestra SOLO esta vez; "
        "en Leo queda únicamente su hash."
    )


class SecretRotated(BaseModel):
    client_id: str
    client_secret: str = Field(description="Nuevo secreto; se muestra SOLO esta vez.")


class ModuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: Name
    description: Description = None


class ModuleUpdate(UpdateModel):
    immutable_fields = ("slug",)
    non_nullable_fields = ("name",)

    name: Name | None = None
    description: Description = None


class ActionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verb: Slug
    name: ActionName = Field(
        description="Nombre legible en español que verá quien administra roles "
        "(p. ej. «Consultar muestras»). Único dentro del módulo.",
        examples=["Consultar muestras"],
    )
    description: Description = None


class ActionUpdate(UpdateModel):
    immutable_fields = ("verb", "tag")
    non_nullable_fields = ("name",)

    name: ActionName | None = None
    description: Description = None


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    module_id: UUID
    verb: str
    tag: str
    name: str
    description: str | None
    is_active: bool


class ModuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    slug: str
    name: str
    description: str | None
    is_active: bool


class ModuleWithActions(ModuleRead):
    actions: list[ActionRead] = Field(default_factory=list)


class ApplicationDetail(ApplicationRead):
    modules: list[ModuleWithActions] = Field(default_factory=list)


# --- sincronizacion de catalogo (la app publica sus tags) ---


class CatalogAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verb: Slug
    name: ActionName | None = Field(
        default=None,
        description="Nombre legible en español. Opcional: al crear la acción, "
        "si falta se deriva del verbo (`rotate-secret` -> «Rotate secret»). Al "
        "sincronizar una acción existente solo se aplica si su nombre aún es el "
        "derivado (no pisa lo que un admin editó).",
    )
    description: Description = None


class CatalogModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: Name
    description: Description = None
    actions: list[CatalogAction] = Field(default_factory=list, max_length=200)


class CatalogSync(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modules: list[CatalogModule] = Field(max_length=200)
    deactivate_missing: bool = Field(
        default=False,
        description="true = desactiva módulos y acciones existentes que no vengan "
        "en este catálogo. Por defecto no se desactiva nada.",
    )

    @model_validator(mode="after")
    def _unique_slugs_and_verbs(self) -> "CatalogSync":
        slugs = [m.slug for m in self.modules]
        if len(slugs) != len(set(slugs)):
            raise ValueError("Hay módulos repetidos en el catálogo.")
        for module in self.modules:
            verbs = [a.verb for a in module.actions]
            if len(verbs) != len(set(verbs)):
                raise ValueError(
                    f"Hay acciones repetidas en el módulo «{module.slug}»."
                )
        return self


class CatalogSyncResult(BaseModel):
    created_modules: list[str] = Field(default_factory=list)
    updated_modules: list[str] = Field(default_factory=list)
    deactivated_modules: list[str] = Field(default_factory=list)
    created_actions: list[str] = Field(default_factory=list)
    updated_actions: list[str] = Field(default_factory=list)
    deactivated_actions: list[str] = Field(default_factory=list)
