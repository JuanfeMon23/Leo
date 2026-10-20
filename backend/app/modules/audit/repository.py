"""Consultas del modulo `audit`. Solo INSERT y SELECT: la BD rechaza UPDATE,
DELETE y TRUNCATE (SQLSTATE `LEO01`)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.applications.models import Application
from app.modules.audit.models import AuditEvent


@dataclass(frozen=True)
class AuditFilters:
    actor_user_id: UUID | None = None
    actor_username: str | None = None
    application_id: UUID | None = None
    module: str | None = None
    action_tag: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    result: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


_EQUALS = {
    "actor_user_id": AuditEvent.actor_user_id,
    "actor_username": AuditEvent.actor_username,
    "application_id": AuditEvent.application_id,
    "module": AuditEvent.module,
    "action_tag": AuditEvent.action_tag,
    "entity_type": AuditEvent.entity_type,
    "entity_id": AuditEvent.entity_id,
    "result": AuditEvent.result,
}


def filtered(filters: AuditFilters) -> Select:
    stmt = select(AuditEvent)
    for name, column in _EQUALS.items():
        value = getattr(filters, name)
        if value is not None:
            stmt = stmt.where(column == value)
    if filters.date_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at < filters.date_to)
    return stmt


ORDER = (AuditEvent.occurred_at.desc(), AuditEvent.id.desc())


async def fetch_for_export(
    session: AsyncSession, filters: AuditFilters, limit: int
) -> list[tuple[AuditEvent, str]]:
    stmt = (
        filtered(filters)
        .add_columns(Application.slug)
        .join(Application, Application.id == AuditEvent.application_id)
        .order_by(*ORDER)
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return [(event, slug) for event, slug in rows.all()]


async def insert(session: AsyncSession, event: AuditEvent) -> AuditEvent:
    session.add(event)
    await session.flush()
    return event
