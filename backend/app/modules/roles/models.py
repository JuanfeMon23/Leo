"""Tablas del modulo `roles`: roles por aplicacion y sus acciones.

Regla "rol <-> accion de la misma app" (Decision roles por aplicacion):
`role_actions` repite `application_id` y lo usa en dos FK compuestas, a
`roles(id, application_id)` y a `actions(id, application_id)`. Una accion de
otra app no satisface ambas a la vez, asi que PostgreSQL la rechaza (SQLSTATE
23503) sin triggers.
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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.checks import not_blank_check, slug_check
from app.core.db.mixins import ActivatableMixin, Timestamps, UUIDv7PK


class Role(UUIDv7PK, Timestamps, ActivatableMixin, Base):
    """Rol de UNA aplicacion (estilo client-roles)."""

    __tablename__ = "roles"
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


class RoleAction(UUIDv7PK, Timestamps, Base):
    """Accion asignada a un rol; solo acciones de la app del rol.

    Quitar una accion de un rol = borrar la fila (la asignacion no la
    referencia nadie; el cambio queda en `audit_events`).
    """

    __tablename__ = "role_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["role_id", "application_id"],
            ["roles.id", "roles.application_id"],
            name="fk_role_actions_role_id_roles",
        ),
        ForeignKeyConstraint(
            ["action_id", "application_id"],
            ["actions.id", "actions.application_id"],
            name="fk_role_actions_action_id_actions",
        ),
        UniqueConstraint("role_id", "action_id"),
        Index("ix_role_actions_action_id", "action_id"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )


class ServiceGrant(UUIDv7PK, Timestamps, Base):
    """Rol de OTRA app concedido a una app llamadora (credenciales de
    servicio): los permisos que Leo le reconoce a la llamadora sobre la app
    destino son las acciones de estos roles.

    `application_id` es la app destino (= app del rol): la FK compuesta
    `(role_id, application_id)` -> `roles(id, application_id)` impide conceder
    un rol que no sea de la destino, como en `role_actions`. Una app no se
    concede acceso a si misma. Revocar = borrar la fila (queda en auditoria).
    """

    __tablename__ = "service_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["role_id", "application_id"],
            ["roles.id", "roles.application_id"],
            name="fk_service_grants_role_id_roles",
        ),
        UniqueConstraint("caller_application_id", "role_id"),
        CheckConstraint(
            "caller_application_id <> application_id",
            name="caller_differs_from_target",
        ),
        Index("ix_service_grants_role_id", "role_id"),
    )

    caller_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
