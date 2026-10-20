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
)

router = APIRouter(tags=["roles"])

Editor = Annotated[Actor, require_actor("leo.roles.edit")]
Deactivator = Annotated[Actor, require_actor("leo.roles.deactivate")]


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
