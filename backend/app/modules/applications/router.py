"""Rutas `/api/v1/applications`: apps cliente, modulos, acciones y
sincronizacion de catalogo."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, status

from app.core.audit import Actor
from app.core.authz import require_action, require_actor
from app.core.client_auth import AuthenticatedClient
from app.core.database import SessionDep
from app.core.pagination import ActiveQuery, PaginationDep, SearchQuery
from app.core.request_meta import Meta
from app.core.schemas import AUTH_ERRORS, Page, error_responses
from app.modules.applications import controller
from app.modules.applications.schemas import (
    ActionCreate,
    ActionRead,
    ActionUpdate,
    ApplicationCreate,
    ApplicationCreated,
    ApplicationDetail,
    ApplicationRead,
    ApplicationUpdate,
    CatalogSync,
    CatalogSyncResult,
    ModuleCreate,
    ModuleRead,
    ModuleUpdate,
    SecretRotated,
)

router = APIRouter(tags=["applications"])

Creator = Annotated[Actor, require_actor("leo.applications.create")]
Editor = Annotated[Actor, require_actor("leo.applications.edit")]
Deactivator = Annotated[Actor, require_actor("leo.applications.deactivate")]


@router.get(
    "",
    response_model=Page[ApplicationRead],
    dependencies=[require_action("leo.applications.view")],
    responses=error_responses(*AUTH_ERRORS),
)
async def list_applications(
    session: SessionDep,
    pagination: PaginationDep,
    q: SearchQuery = None,
    active: ActiveQuery = None,
) -> Page[ApplicationRead]:
    return await controller.list_applications(session, q, active, pagination)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApplicationCreated,
    responses=error_responses(*AUTH_ERRORS, 409, 422),
    summary="Registrar una app (devuelve el client_secret UNA vez)",
)
async def create_application(
    session: SessionDep, data: ApplicationCreate, actor: Creator
) -> ApplicationCreated:
    return await controller.create_application(session, data, actor)


@router.get(
    "/{app_id}",
    response_model=ApplicationDetail,
    dependencies=[require_action("leo.applications.view")],
    responses=error_responses(*AUTH_ERRORS, 404),
    summary="Detalle de una app con sus módulos y acciones",
)
async def get_application(session: SessionDep, app_id: UUID) -> ApplicationDetail:
    return await controller.get_application(session, app_id)


@router.patch(
    "/{app_id}",
    response_model=ApplicationRead,
    responses=error_responses(*AUTH_ERRORS, 404, 422),
)
async def update_application(
    session: SessionDep, app_id: UUID, data: ApplicationUpdate, actor: Editor
) -> ApplicationRead:
    return await controller.update_application(session, app_id, data, actor)


@router.post(
    "/{app_id}/deactivate",
    response_model=ApplicationRead,
    responses=error_responses(*AUTH_ERRORS, 404, 409),
)
async def deactivate_application(
    session: SessionDep, app_id: UUID, actor: Deactivator
) -> ApplicationRead:
    return await controller.set_application_active(session, app_id, False, actor)


@router.post(
    "/{app_id}/activate",
    response_model=ApplicationRead,
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def activate_application(
    session: SessionDep, app_id: UUID, actor: Deactivator
) -> ApplicationRead:
    return await controller.set_application_active(session, app_id, True, actor)


@router.post(
    "/{app_id}/rotate-secret",
    response_model=SecretRotated,
    responses=error_responses(*AUTH_ERRORS, 404),
    summary="Regenerar el client_secret (devuelve el nuevo UNA vez)",
)
async def rotate_secret(
    session: SessionDep,
    app_id: UUID,
    actor: Annotated[Actor, require_actor("leo.applications.rotate-secret")],
) -> SecretRotated:
    return await controller.rotate_secret(session, app_id, actor)


@router.post(
    "/{app_id}/modules",
    status_code=status.HTTP_201_CREATED,
    response_model=ModuleRead,
    responses=error_responses(*AUTH_ERRORS, 404, 409, 422),
)
async def create_module(
    session: SessionDep, app_id: UUID, data: ModuleCreate, actor: Creator
) -> ModuleRead:
    return await controller.create_module(session, app_id, data, actor)


@router.patch(
    "/{app_id}/modules/{module_id}",
    response_model=ModuleRead,
    responses=error_responses(*AUTH_ERRORS, 404, 422),
)
async def update_module(
    session: SessionDep,
    app_id: UUID,
    module_id: UUID,
    data: ModuleUpdate,
    actor: Editor,
) -> ModuleRead:
    return await controller.update_module(session, app_id, module_id, data, actor)


@router.post(
    "/{app_id}/modules/{module_id}/deactivate",
    response_model=ModuleRead,
    responses=error_responses(*AUTH_ERRORS, 404, 409),
)
async def deactivate_module(
    session: SessionDep, app_id: UUID, module_id: UUID, actor: Deactivator
) -> ModuleRead:
    return await controller.set_module_active(session, app_id, module_id, False, actor)


@router.post(
    "/{app_id}/modules/{module_id}/activate",
    response_model=ModuleRead,
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def activate_module(
    session: SessionDep, app_id: UUID, module_id: UUID, actor: Deactivator
) -> ModuleRead:
    return await controller.set_module_active(session, app_id, module_id, True, actor)


@router.post(
    "/{app_id}/modules/{module_id}/actions",
    status_code=status.HTTP_201_CREATED,
    response_model=ActionRead,
    responses=error_responses(*AUTH_ERRORS, 404, 409, 422),
    summary="Crear una acción (el tag se arma como <app>.<módulo>.<verbo>)",
)
async def create_action(
    session: SessionDep,
    app_id: UUID,
    module_id: UUID,
    data: ActionCreate,
    actor: Creator,
) -> ActionRead:
    return await controller.create_action(session, app_id, module_id, data, actor)


@router.patch(
    "/{app_id}/actions/{action_id}",
    response_model=ActionRead,
    responses=error_responses(*AUTH_ERRORS, 404, 409, 422),
    summary="Editar nombre/descripción de una acción (verbo y tag son inmutables; "
    "las acciones de evento no se editan)",
)
async def update_action(
    session: SessionDep,
    app_id: UUID,
    action_id: UUID,
    data: ActionUpdate,
    actor: Editor,
) -> ActionRead:
    return await controller.update_action(session, app_id, action_id, data, actor)


@router.post(
    "/{app_id}/actions/{action_id}/deactivate",
    response_model=ActionRead,
    responses=error_responses(*AUTH_ERRORS, 404, 409),
)
async def deactivate_action(
    session: SessionDep, app_id: UUID, action_id: UUID, actor: Deactivator
) -> ActionRead:
    return await controller.set_action_active(session, app_id, action_id, False, actor)


@router.post(
    "/{app_id}/actions/{action_id}/activate",
    response_model=ActionRead,
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def activate_action(
    session: SessionDep, app_id: UUID, action_id: UUID, actor: Deactivator
) -> ActionRead:
    return await controller.set_action_active(session, app_id, action_id, True, actor)


@router.put(
    "/{slug}/catalog",
    response_model=CatalogSyncResult,
    responses=error_responses(401, 403, 404, 409, 422),
    summary="Sincronizar el catálogo de módulos y acciones de una app "
    "(client credentials de esa app, HTTP Basic)",
    description="Cada acción puede traer `name` (nombre legible, opcional). Al "
    "crearla se usa el declarado o, si falta, el derivado del verbo. En una "
    "acción existente solo se reemplaza si el nombre guardado aún es el "
    "derivado (no pisa nombres editados por un admin). Nombre repetido en el "
    "módulo: 409 `duplicate` con `details.name`.",
)
async def sync_catalog(
    session: SessionDep,
    slug: str,
    data: CatalogSync,
    client: AuthenticatedClient,
    meta: Meta,
) -> CatalogSyncResult:
    return await controller.sync_catalog(session, slug, client, data, meta.request_id)
