"""Mixins reutilizables por los modelos de todos los modulos.

Todo bloque de columnas que se repite en 2+ tablas vive aqui.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class UUIDv7PK:
    """PK `id uuid` con `uuidv7()` (nativa de PostgreSQL 18, ordenada por
    tiempo). Tambien en las tablas intermedias (la pareja va en `UNIQUE`)."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )


class Timestamps:
    """`created_at` / `updated_at` en toda tabla (excepto `audit_events`)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ActivatableMixin:
    """`is_active`: apps, modulos, acciones, roles y usuarios se desactivan,
    nunca se borran (los referencian la auditoria y las sesiones)."""

    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), nullable=False
    )
