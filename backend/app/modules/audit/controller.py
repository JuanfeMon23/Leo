"""Casos de uso de `audit`: escribir eventos (para todos los modulos),
consultarlos, exportarlos e ingerir los que envian las otras apps."""

import csv
import io
import json
from typing import Any
from uuid import UUID

from sqlalchemy import null
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import runtime_settings
from app.core.audit import Actor, AuditEntry, diff, is_sensitive, json_safe, snapshot
from app.core.authz import Principal
from app.core.client_auth import ClientApp
from app.core.exceptions import ForbiddenError, ValidationAppError
from app.core.pagination import Pagination, paginate
from app.core.request_meta import RequestMeta
from app.core.schemas import Page
from app.core.service_authz import ServicePrincipal
from app.modules import applications, auth, roles, users
from app.modules.audit import repository
from app.modules.audit.models import AuditEvent, AuditResult
from app.modules.audit.repository import AuditFilters
from app.modules.audit.schemas import AuditEventIngest, AuditEventRead

EXPORT_COLUMNS = (
    "occurred_at",
    "application",
    "module",
    "action_tag",
    "result",
    "actor_username",
    "actor_user_id",
    "entity_type",
    "entity_id",
    "reason",
    "changes",
    "ip",
    "user_agent",
    "session_id",
    "request_id",
)
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


async def record_event(session: AsyncSession, entry: AuditEntry) -> UUID:
    """Agrega el evento a la transaccion en curso (sin commit): queda
    atomico con la mutacion que audita. Sin `application_id` -> app `leo`."""
    app_id = entry.application_id or await applications.leo_application_id(session)
    event = AuditEvent(
        actor_user_id=entry.actor_user_id,
        actor_username=entry.actor_username,
        application_id=app_id,
        module=entry.action_tag.split(".")[1],
        action_tag=entry.action_tag,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        # null() = NULL de SQL (None seria el JSON `null`, que el CHECK rechaza).
        changes=json_safe(entry.changes) if entry.changes else null(),
        result=AuditResult(entry.result),
        reason=entry.reason,
        ip=entry.ip,
        user_agent=entry.user_agent,
        session_id=entry.session_id,
        request_id=entry.request_id,
    )
    await repository.insert(session, event)
    return event.id


async def record_change(
    session: AsyncSession,
    actor: Actor,
    tag: str,
    entity_type: str,
    entity: Any,
    before: dict[str, Any] | None,
    fields: tuple[str, ...],
) -> None:
    """Flush + refresh de `entity` y evento con el diff before/after de esos
    campos (si algo cambio). Sin commit: lo hace el caso de uso."""
    await session.flush()
    await session.refresh(entity)
    changes = diff(before, snapshot(entity, fields))
    if changes:
        await record_event(
            session,
            actor.entry(
                tag, entity_type=entity_type, entity_id=str(entity.id), changes=changes
            ),
        )


async def record_and_commit(session: AsyncSession, entry: AuditEntry) -> None:
    """Para eventos de peticiones que van a fallar (403, login fallido...):
    se confirma antes de lanzar el error, para que no se pierda."""
    await record_event(session, entry)
    await session.commit()


async def record_denied(
    session: AsyncSession, principal: Principal, tag: str, meta: RequestMeta
) -> None:
    """Hook de `require_action` (configurado en `app/main.py`)."""
    actor = Actor(principal.user_id, principal.username, principal.session_id, meta)
    await record_and_commit(
        session,
        actor.entry(tag, result="denied", reason="No tiene el permiso requerido."),
    )


async def record_service_denied(
    session: AsyncSession, principal: ServicePrincipal, tag: str, meta: RequestMeta
) -> None:
    """Hook de `require_service_actor` (configurado en `app/main.py`)."""
    actor = Actor(None, principal.actor_name, None, meta)
    await record_and_commit(
        session,
        actor.entry(
            tag,
            result="denied",
            entity_type="application",
            entity_id=str(principal.application_id),
            reason="La aplicación no tiene el permiso de servicio requerido.",
        ),
    )


async def list_events(
    session: AsyncSession, filters: AuditFilters, pagination: Pagination
) -> Page[AuditEventRead]:
    return await paginate(
        session,
        repository.filtered(filters),
        pagination,
        AuditEventRead,
        *repository.ORDER,
    )


def _csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(json_safe(value))
    # Evita inyeccion de formulas al abrir el CSV en una hoja de calculo.
    return "'" + text if text.startswith(_CSV_FORMULA_PREFIXES) else text


async def export_csv(session: AsyncSession, filters: AuditFilters, actor: Actor) -> str:
    max_rows = await runtime_settings.get("audit.export_max_rows")
    rows = await repository.fetch_for_export(session, filters, max_rows)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for event, app_slug in rows:
        values = {
            **{c: getattr(event, c, None) for c in EXPORT_COLUMNS},
            "application": app_slug,
        }
        writer.writerow([_csv_cell(values[c]) for c in EXPORT_COLUMNS])
    await record_event(
        session,
        actor.entry(
            "leo.audit.export",
            entity_type="audit_event",
            reason=f"Exportó {len(rows)} eventos.",
            changes={
                "filters": {
                    "before": None,
                    "after": {k: v for k, v in vars(filters).items() if v is not None},
                }
            },
        ),
    )
    await session.commit()
    return buffer.getvalue()


async def ingest_event(
    session: AsyncSession, client: ClientApp, data: AuditEventIngest
) -> UUID:
    """Evento enviado por el backend de una app. Solo tags de SU app; el
    actor se valida (token de esa app atado al jkt, o usuario con acceso)."""
    if not data.action_tag.startswith(f"{client.slug}."):
        raise ForbiddenError(
            "Solo puedes registrar eventos de tu propia aplicación "
            f"(tags «{client.slug}.*»).",
            {"action_tag": data.action_tag},
            code="foreign_action_tag",
        )
    actor_id: UUID | None = None
    actor_username: str | None = None
    session_id: UUID | None = None
    if data.actor is not None:
        owner = await auth.resolve_access_token(
            session, client.id, data.actor.access_token, data.actor.jkt, touch=False
        )
        if owner is None:
            raise ValidationAppError(
                "El token del actor no es válido, expiró o no corresponde a esta "
                "aplicación.",
                code="invalid_actor",
            )
        actor_id, actor_username, session_id = (
            owner.user_id,
            owner.username,
            owner.session_id,
        )
    elif data.actor_user_id is not None:
        identity = await users.get_identity(session, data.actor_user_id)
        if identity is None or not await roles.has_access(
            session, identity.id, client.id
        ):
            raise ValidationAppError(
                "El usuario actor no existe o no tiene acceso a esta aplicación.",
                {"actor_user_id": str(data.actor_user_id)},
                code="invalid_actor",
            )
        actor_id, actor_username = identity.id, identity.username

    event_id = await record_event(
        session,
        AuditEntry(
            action_tag=data.action_tag,
            result=data.result,
            actor_user_id=actor_id,
            actor_username=actor_username,
            application_id=client.id,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            changes={
                k: v for k, v in (data.changes or {}).items() if not is_sensitive(k)
            }
            or None,
            reason=data.reason,
            ip=str(data.ip) if data.ip else None,
            user_agent=data.user_agent,
            session_id=session_id,
            request_id=data.request_id,
        ),
    )
    await session.commit()
    return event_id
