"""Tablas del modulo `applications`: apps cliente, sus modulos y acciones.

`(id, application_id)` es UNIQUE en `app_modules` y `actions` para que otras
tablas (actions, role_actions) puedan exigir con FK compuesta que lo que
referencian pertenece a la misma aplicacion.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.checks import (
    action_tag_check,
    not_blank_check,
    sha256_hex_check,
    slug_check,
)
from app.core.db.mixins import ActivatableMixin, Timestamps, UUIDv7PK


class Application(UUIDv7PK, Timestamps, ActivatableMixin, Base):
    """App cliente del ecosistema (Leo incluida, como `leo`)."""

    __tablename__ = "applications"
    __table_args__ = (
        slug_check(),
        sha256_hex_check("client_secret_hash"),
        not_blank_check("name"),
    )

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    # Coincidencia exacta: `/authorize` solo acepta una de estas URIs.
    redirect_uris: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # SHA-256 hex del client_secret (256 bits aleatorios); nunca en claro.
    client_secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AppModule(UUIDv7PK, Timestamps, ActivatableMixin, Base):
    """Modulo de una app (segundo segmento del tag de accion)."""

    __tablename__ = "app_modules"
    __table_args__ = (
        UniqueConstraint("application_id", "slug"),
        UniqueConstraint("id", "application_id"),
        slug_check(),
        not_blank_check("name"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Action(UUIDv7PK, Timestamps, ActivatableMixin, Base):
    """Accion protegible; `tag` = `<app>.<modulo>.<verbo>`, unico global;
    `name` = nombre legible, unico por modulo.

    `application_id` se repite (denormalizado) para las FK compuestas: la de
    aqui garantiza que el modulo es de esa app, y la de `role_actions` que el
    rol y la accion son de la misma app.
    """

    __tablename__ = "actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["module_id", "application_id"],
            ["app_modules.id", "app_modules.application_id"],
            name="fk_actions_module_id_app_modules",
        ),
        UniqueConstraint("module_id", "verb"),
        UniqueConstraint("module_id", "name", name="uq_actions_module_id_name"),
        UniqueConstraint("id", "application_id"),
        slug_check("verb"),
        not_blank_check("name"),
        action_tag_check("tag"),
        CheckConstraint("split_part(tag, '.', 3) = verb", name="tag_ends_with_verb"),
        Index("ix_actions_application_id", "application_id"),
    )

    # Sin FK simple a `applications`: la FK compuesta con `app_modules` ya la
    # implica (el modulo existe y es de esa app).
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    module_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    verb: Mapped[str] = mapped_column(String(64), nullable=False)
    tag: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    # Nombre legible para quien administra roles; el tag sigue siendo el
    # identificador. Unico dentro del modulo.
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
