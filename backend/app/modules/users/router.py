"""Rutas `/api/v1/users`."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, status

from app.core.audit import Actor
from app.core.authz import require_action, require_actor
from app.core.database import SessionDep
from app.core.pagination import ActiveQuery, PaginationDep, SearchQuery
from app.core.schemas import AUTH_ERRORS, Page, error_responses
from app.modules.users import controller
from app.modules.users.schemas import (
    PasswordReset,
    UserCreate,
    UserDetail,
    UserRead,
    UserRolesAdd,
    UserUpdate,
)

router = APIRouter(tags=["users"])

Deactivator = Annotated[Actor, require_actor("leo.users.deactivate")]
RoleAssigner = Annotated[Actor, require_actor("leo.users.assign-roles")]


@router.get(
    "",
    response_model=Page[UserRead],
    dependencies=[require_action("leo.users.view")],
    responses=error_responses(*AUTH_ERRORS),
)
async def list_users(
    session: SessionDep,
    pagination: PaginationDep,
    q: SearchQuery = None,
    active: ActiveQuery = None,
) -> Page[UserRead]:
    return await controller.list_users(session, q, active, pagination)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=UserRead,
    responses=error_responses(*AUTH_ERRORS, 409, 422),
)
async def create_user(
    session: SessionDep,
    data: UserCreate,
    actor: Annotated[Actor, require_actor("leo.users.create")],
) -> UserRead:
    return await controller.create_user(session, data, actor)


@router.get(
    "/{user_id}",
    response_model=UserDetail,
    dependencies=[require_action("leo.users.view")],
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def get_user(session: SessionDep, user_id: UUID) -> UserDetail:
    return await controller.get_user(session, user_id)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    responses=error_responses(*AUTH_ERRORS, 404, 409, 422),
)
async def update_user(
    session: SessionDep,
    user_id: UUID,
    data: UserUpdate,
    actor: Annotated[Actor, require_actor("leo.users.edit")],
) -> UserRead:
    return await controller.update_user(session, user_id, data, actor)


@router.post(
    "/{user_id}/deactivate",
    response_model=UserRead,
    responses=error_responses(*AUTH_ERRORS, 404, 409),
    summary="Desactivar (revoca todas sus sesiones de inmediato)",
)
async def deactivate_user(
    session: SessionDep, user_id: UUID, actor: Deactivator
) -> UserRead:
    return await controller.set_user_active(session, user_id, False, actor)


@router.post(
    "/{user_id}/activate",
    response_model=UserRead,
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def activate_user(
    session: SessionDep, user_id: UUID, actor: Deactivator
) -> UserRead:
    return await controller.set_user_active(session, user_id, True, actor)


@router.post(
    "/{user_id}/unlock",
    response_model=UserRead,
    responses=error_responses(*AUTH_ERRORS, 404),
    summary="Desbloquear (borra intentos fallidos y bloqueo)",
)
async def unlock_user(
    session: SessionDep,
    user_id: UUID,
    actor: Annotated[Actor, require_actor("leo.users.unlock")],
) -> UserRead:
    return await controller.unlock_user(session, user_id, actor)


@router.post(
    "/{user_id}/reset-password",
    response_model=UserRead,
    responses=error_responses(*AUTH_ERRORS, 404, 422),
    summary="Asignar contraseña nueva (revoca todas sus sesiones)",
)
async def reset_password(
    session: SessionDep,
    user_id: UUID,
    data: PasswordReset,
    actor: Annotated[Actor, require_actor("leo.users.reset-password")],
) -> UserRead:
    return await controller.reset_password(session, user_id, data, actor)


@router.post(
    "/{user_id}/roles",
    response_model=UserDetail,
    responses=error_responses(*AUTH_ERRORS, 404, 422),
)
async def add_roles(
    session: SessionDep, user_id: UUID, data: UserRolesAdd, actor: RoleAssigner
) -> UserDetail:
    return await controller.add_roles(session, user_id, data, actor)


@router.delete(
    "/{user_id}/roles/{role_id}",
    response_model=UserDetail,
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def remove_role(
    session: SessionDep, user_id: UUID, role_id: UUID, actor: RoleAssigner
) -> UserDetail:
    return await controller.remove_role(session, user_id, role_id, actor)
