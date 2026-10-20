"""Rutas `/api/v1/roles`."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.audit import Actor
from app.core.authz import require_action, require_actor
from app.core.database import SessionDep
from app.core.pagination import ActiveQuery, PaginationDep, SearchQuery
from app.core.schemas import AUTH_ERRORS, Page, error_responses
from app.modules.roles import controller
from app.modules.roles.schemas import (
    RoleActionsAdd,
    RoleCreate,
    RoleDetail,
    RoleRead,
    RoleUpdate,
    ServiceAccessGrant,
    ServiceCallerRead,
    ServiceGrantRead,
)

router = APIRouter(tags=["roles"])

Editor = Annotated[Actor, require_actor("leo.roles.edit")]
Deactivator = Annotated[Actor, require_actor("leo.roles.deactivate")]
ServiceGranter = Annotated[
    Actor, require_actor("leo.applications.grant-service-access")
]

# Acceso entre servicios: la dueña es `roles` (tabla `service_grants`), pero la
# ruta cuelga de la app llamadora: `main.py` lo monta bajo `/api/v1/applications`.
service_access_router = APIRouter(tags=["service-access"])


@router.get(
    "",
    response_model=Page[RoleRead],
    dependencies=[require_action("leo.roles.view")],
    responses=error_responses(*AUTH_ERRORS),
)
async def list_roles(
    session: SessionDep,
    pagination: PaginationDep,
    application_id: Annotated[UUID | None, Query()] = None,
    q: SearchQuery = None,
    active: ActiveQuery = None,
) -> Page[RoleRead]:
    return await controller.list_roles(session, application_id, q, active, pagination)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RoleRead,
    responses=error_responses(*AUTH_ERRORS, 409, 422),
)
async def create_role(
    session: SessionDep,
    data: RoleCreate,
    actor: Annotated[Actor, require_actor("leo.roles.create")],
) -> RoleRead:
    return await controller.create_role(session, data, actor)


@router.get(
    "/{role_id}",
    response_model=RoleDetail,
    dependencies=[require_action("leo.roles.view")],
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def get_role(session: SessionDep, role_id: UUID) -> RoleDetail:
    return await controller.get_role(session, role_id)


@router.patch(
    "/{role_id}",
    response_model=RoleRead,
    responses=error_responses(*AUTH_ERRORS, 404, 422),
)
async def update_role(
    session: SessionDep, role_id: UUID, data: RoleUpdate, actor: Editor
) -> RoleRead:
    return await controller.update_role(session, role_id, data, actor)


@router.post(
    "/{role_id}/deactivate",
    response_model=RoleRead,
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def deactivate_role(
    session: SessionDep, role_id: UUID, actor: Deactivator
) -> RoleRead:
    return await controller.set_role_active(session, role_id, False, actor)


@router.post(
    "/{role_id}/activate",
    response_model=RoleRead,
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def activate_role(
    session: SessionDep, role_id: UUID, actor: Deactivator
) -> RoleRead:
    return await controller.set_role_active(session, role_id, True, actor)


@router.post(
    "/{role_id}/actions",
    response_model=RoleDetail,
    responses=error_responses(*AUTH_ERRORS, 404, 422),
    summary="Asignar acciones (solo de la app del rol)",
)
async def add_actions(
    session: SessionDep, role_id: UUID, data: RoleActionsAdd, actor: Editor
) -> RoleDetail:
    return await controller.add_actions(session, role_id, data, actor)


@router.delete(
    "/{role_id}/actions/{action_id}",
    response_model=RoleDetail,
    responses=error_responses(*AUTH_ERRORS, 404),
    summary="Quitar una acción del rol",
)
async def remove_action(
    session: SessionDep, role_id: UUID, action_id: UUID, actor: Editor
) -> RoleDetail:
    return await controller.remove_action(session, role_id, action_id, actor)


@router.get(
    "/{role_id}/service-callers",
    response_model=list[ServiceCallerRead],
    dependencies=[require_action("leo.applications.grant-service-access")],
    responses=error_responses(*AUTH_ERRORS, 404),
    summary="Apps llamadoras a las que se concedió este rol (acceso entre servicios)",
)
async def list_service_callers(
    session: SessionDep, role_id: UUID
) -> list[ServiceCallerRead]:
    return await controller.list_service_callers(session, role_id)


@service_access_router.get(
    "/{app_id}/service-access",
    response_model=list[ServiceGrantRead],
    dependencies=[require_action("leo.applications.grant-service-access")],
    responses=error_responses(*AUTH_ERRORS, 404),
    summary="Roles de otras apps concedidos a esta app llamadora",
    description="Un token de servicio de esta app para la app destino lleva como "
    "permisos las acciones activas de estos roles activos (calculadas al "
    "introspeccionar).",
)
async def list_service_access(
    session: SessionDep, app_id: UUID
) -> list[ServiceGrantRead]:
    return await controller.list_service_access(session, app_id)


@service_access_router.post(
    "/{app_id}/service-access",
    response_model=list[ServiceGrantRead],
    responses=error_responses(*AUTH_ERRORS, 404, 422),
    summary="Conceder roles de otras apps a esta app llamadora",
    description="Todo o nada. Los roles deben existir, estar activos y ser de una "
    "app distinta de la llamadora (y no de `leo`). Conceder un rol ya concedido "
    "no hace nada. Devuelve la lista completa resultante.",
)
async def grant_service_access(
    session: SessionDep, app_id: UUID, data: ServiceAccessGrant, actor: ServiceGranter
) -> list[ServiceGrantRead]:
    return await controller.grant_service_access(session, app_id, data, actor)


@service_access_router.delete(
    "/{app_id}/service-access/{role_id}",
    response_model=list[ServiceGrantRead],
    responses=error_responses(*AUTH_ERRORS, 404),
    summary="Retirar un rol concedido a esta app llamadora",
    description="Si a la llamadora no le queda ningún rol activo de esa app "
    "destino, sus tokens de servicio vigentes hacia ella se revocan de inmediato. "
    "Devuelve la lista restante.",
)
async def revoke_service_access(
    session: SessionDep, app_id: UUID, role_id: UUID, actor: ServiceGranter
) -> list[ServiceGrantRead]:
    return await controller.revoke_service_access(session, app_id, role_id, actor)
