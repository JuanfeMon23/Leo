"""Tabla del modulo `audit`: eventos de auditoria del ecosistema.

Append-only garantizado por la BD: triggers `trg_audit_events_append_only`
(UPDATE/DELETE) y `trg_audit_events_no_truncate` (TRUNCATE) lanzan SQLSTATE
`LEO01` (`app.core.db.triggers.APPEND_ONLY_SQLSTATE`). Sin `updated_at`.
Actor, modulo y tag se guardan como snapshot de texto: el evento conserva lo
que paso aunque despues cambien el usuario o el catalogo de acciones.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base
from app.core.db.checks import action_tag_check
from app.core.db.mixins import UUIDv7PK
from app.core.db.types import str_enum


class AuditResult(enum.StrEnum):
    OK = "ok"
    DENIED = "denied"
    ERROR = "error"


class AuditEvent(UUIDv7PK, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        action_tag_check("action_tag"),
        CheckConstraint(
            "changes IS NULL OR jsonb_typeof(changes) = 'object'",
            name="changes_is_object",
        ),
        # Consultas del visor: por fecha, y por actor / app / tag ordenadas
        # por fecha (el btree se recorre en ambos sentidos).
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index(
            "ix_audit_events_actor_user_id_occurred_at", "actor_user_id", "occurred_at"
        ),
        Index(
            "ix_audit_events_application_id_occurred_at",
            "application_id",
            "occurred_at",
        ),
        Index("ix_audit_events_action_tag_occurred_at", "action_tag", "occurred_at"),
        Index("ix_audit_events_session_id", "session_id"),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # NULL: evento sin usuario autenticado (p. ej. login fallido).
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    actor_username: Mapped[str | None] = mapped_column(String(64))
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False
    )
    module: Mapped[str | None] = mapped_column(String(64))
    action_tag: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    # Texto: las apps del ecosistema pueden no usar uuid.
    entity_id: Mapped[str | None] = mapped_column(String(64))
    # `{campo: {before, after}}`; nunca tokens ni secretos.
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[AuditResult] = mapped_column(
        str_enum(AuditResult, "result", 16), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id")
    )
    request_id: Mapped[str | None] = mapped_column(String(64))
