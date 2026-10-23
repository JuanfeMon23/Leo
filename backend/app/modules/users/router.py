"""Rutas `/api/v1/users`."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.core.audit import Actor
from app.core.authz import require_action, require_actor
from app.core.database import SessionDep
from app.core.pagination import ActiveQuery, PaginationDep, SearchQuery
from app.core.request_meta import Meta
from app.core.schemas import AUTH_ERRORS, Page, error_responses
from app.core.service_authz import ServiceCaller, require_service_actor
from app.modules.users import controller
from app.modules.users.controller import DELEGATED_TAG, PROVISION_TAG
from app.modules.users.schemas import (
    DelegatedPasswordChange,
    DelegatedProfileRead,
    DelegatedProfileUpdate,
    PasswordReset,
    PatientProvision,
    PatientRead,
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


@router.post(
    "/service/patients",
    status_code=status.HTTP_201_CREATED,
    response_model=PatientRead,
    responses=error_responses(401, 403, 409, 422, 429, 503),
    summary="Crear un paciente (solo apps con credencial de servicio)",
    description="Autenticación: `Authorization: Bearer <token de servicio>` "
    "pedido con `grant_type=client_credentials` y `audience=leo`; la app debe "
    "tener concedido el rol `leo-patient-provisioner` "
    "(`leo.users.provision-patient`). Crea el usuario activo con el rol "
    "`acuarius/paciente`. Duplicados: 409 `conflict` genérico.",
)
async def provision_patient(
    session: SessionDep,
    data: PatientProvision,
    caller: Annotated[ServiceCaller, require_service_actor(PROVISION_TAG)],
) -> PatientRead:
    principal, actor = caller
    return await controller.provision_patient(session, data, principal, actor)


@router.patch(
    "/service/delegated/profile",
    response_model=DelegatedProfileRead,
    responses=error_responses(401, 403, 409, 422, 429),
    summary="Editar el perfil de un usuario en su nombre (solo apps con servicio)",
    description="Autenticación: `Authorization: Bearer <token de servicio>` "
    "(`client_credentials`, `audience=leo`) de una app con el rol "
    "`leo-self-service-delegate` (`leo.users.delegated-self-manage`). El "
    "usuario objetivo sale de `user_access_token` (access token que Leo "
    "emitió al usuario para ESA app; vigente, sesión viva); nunca se acepta un "
    "id (422). Solo cuentas SIN permisos ni roles de Leo (403 genérico si no). "
    "Mismas reglas que `PATCH /auth/me/profile`: otro correo exige "
    "`current_password` (422 `current_password_required`, 403 "
    "`invalid_current_password`, 429 `too_many_attempts`), 409 `duplicate`, "
    "cierra las demás sesiones al cambiar el correo. Token de usuario "
    "inválido: 401 `invalid_token` (`details.field=user_access_token`).",
)
async def delegated_update_profile(
    session: SessionDep,
    data: DelegatedProfileUpdate,
    caller: Annotated[ServiceCaller, require_service_actor(DELEGATED_TAG)],
    meta: Meta,
) -> DelegatedProfileRead:
    principal, _actor = caller
    return await controller.delegated_update_profile(session, principal, data, meta)


@router.post(
    "/service/delegated/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 422, 429),
    summary="Cambiar la contraseña de un usuario en su nombre (solo apps con servicio)",
    description="Misma autenticación y restricciones que "
    "`PATCH /users/service/delegated/profile`. Mismas reglas que `POST "
    "/auth/me/password`: exige la contraseña actual (401 `invalid_credentials`), "
    "política de contraseñas (422 `weak_password`, `same_password`), 429 "
    "`too_many_attempts` con bloqueo compartido, y cierra las demás sesiones "
    "del usuario (la del token se mantiene).",
)
async def delegated_change_password(
    session: SessionDep,
    data: DelegatedPasswordChange,
    caller: Annotated[ServiceCaller, require_service_actor(DELEGATED_TAG)],
    meta: Meta,
) -> Response:
    principal, _actor = caller
    await controller.delegated_change_password(session, principal, data, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
