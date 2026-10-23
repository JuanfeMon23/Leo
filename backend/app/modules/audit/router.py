"""Rutas `/api/v1/audit`: consulta y export (frontend de Leo) e ingesta de
eventos de las otras apps (client credentials)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.audit import Actor
from app.core.authz import require_action, require_actor
from app.core.client_auth import AuthenticatedClient
from app.core.database import SessionDep
from app.core.pagination import PaginationDep
from app.core.schemas import AUTH_ERRORS, Page, error_responses
from app.modules.audit import controller
from app.modules.audit.repository import AuditFilters
from app.modules.audit.schemas import (
    AuditEventIngest,
    AuditEventIngested,
    AuditEventRead,
    Result,
)

router = APIRouter(tags=["audit"])


def audit_filters(
    actor_user_id: UUID | None = None,
    actor_username: Annotated[str | None, Query(max_length=64)] = None,
    application_id: UUID | None = None,
    module: Annotated[str | None, Query(max_length=64)] = None,
    action_tag: Annotated[str | None, Query(max_length=200)] = None,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    result: Result | None = None,
    date_from: Annotated[
        datetime | None, Query(description="Desde (incluido), ISO 8601.")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Hasta (excluido), ISO 8601.")
    ] = None,
) -> AuditFilters:
    return AuditFilters(
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        application_id=application_id,
        module=module,
        action_tag=action_tag,
        entity_type=entity_type,
        entity_id=entity_id,
        result=result,
        date_from=date_from,
        date_to=date_to,
    )


Filters = Annotated[AuditFilters, Depends(audit_filters)]


@router.get(
    "/events",
    response_model=Page[AuditEventRead],
    dependencies=[require_action("leo.audit.view")],
    responses=error_responses(*AUTH_ERRORS),
    summary="Listar eventos de auditoría (más recientes primero)",
)
async def list_events(
    session: SessionDep, filters: Filters, pagination: PaginationDep
) -> Page[AuditEventRead]:
    return await controller.list_events(session, filters, pagination)


@router.get(
    "/events/export",
    response_class=Response,
    responses={
        200: {"content": {"text/csv": {}}, "description": "CSV (UTF-8)."},
        **error_responses(*AUTH_ERRORS),
    },
    summary="Exportar eventos a CSV (máximo: ajuste audit.export_max_rows)",
)
async def export_events(
    session: SessionDep,
    filters: Filters,
    actor: Annotated[Actor, require_actor("leo.audit.export")],
) -> Response:
    body = await controller.export_csv(session, filters, actor)
    return Response(
        content=body.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="auditoria.csv"'},
    )


@router.post(
    "/events",
    status_code=status.HTTP_201_CREATED,
    response_model=AuditEventIngested,
    responses=error_responses(401, 403, 422),
    summary="Ingerir un evento de una app (client credentials, HTTP Basic)",
)
async def ingest_event(
    session: SessionDep,
    client: AuthenticatedClient,
    data: AuditEventIngest,
) -> AuditEventIngested:
    return AuditEventIngested(id=await controller.ingest_event(session, client, data))
