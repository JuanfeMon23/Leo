"""Rutas `/api/v1/document-types`: catalogo de tipos de documento. Lectura
para cualquier usuario autenticado o app con credencial de servicio; gestion
con permisos `leo.document-types.*`."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.audit import Actor
from app.core.authz import require_actor
from app.core.database import SessionDep
from app.core.schemas import AUTH_ERRORS, error_responses
from app.core.service_authz import UserOrService
from app.modules.users import document_types_controller as controller
from app.modules.users.schemas import (
    DocumentTypeCreate,
    DocumentTypeRead,
    DocumentTypeUpdate,
)

router = APIRouter(tags=["document-types"])

Editor = Annotated[Actor, require_actor("leo.document-types.edit")]
Deactivator = Annotated[Actor, require_actor("leo.document-types.deactivate")]


@router.get(
    "",
    response_model=list[DocumentTypeRead],
    responses=error_responses(*AUTH_ERRORS),
    summary="Listar tipos de documento (usuarios y apps con servicio)",
    description="Ordenado por `sort_order`. Autenticación: sesión SSO (cookie + "
    "DPoP) o `Authorization: Bearer <token de servicio>` "
    "(`client_credentials`, `audience=leo`). `active=true` (por defecto) solo "
    "activos; `active=false` solo inactivos.",
)
async def list_document_types(
    session: SessionDep,
    _principal: UserOrService,
    active: Annotated[
        bool,
        Query(description="true (por defecto) = solo activos; false = solo inactivos."),
    ] = True,
) -> list[DocumentTypeRead]:
    return await controller.list_document_types(session, active)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentTypeRead,
    responses=error_responses(*AUTH_ERRORS, 409, 422),
)
async def create_document_type(
    session: SessionDep,
    data: DocumentTypeCreate,
    actor: Annotated[Actor, require_actor("leo.document-types.create")],
) -> DocumentTypeRead:
    return await controller.create_document_type(session, data, actor)


@router.patch(
    "/{code}",
    response_model=DocumentTypeRead,
    responses=error_responses(*AUTH_ERRORS, 404, 422),
    summary="Editar nombre u orden (el código no cambia)",
)
async def update_document_type(
    session: SessionDep, code: str, data: DocumentTypeUpdate, actor: Editor
) -> DocumentTypeRead:
    return await controller.update_document_type(session, code, data, actor)


@router.post(
    "/{code}/deactivate",
    response_model=DocumentTypeRead,
    responses=error_responses(*AUTH_ERRORS, 404),
    summary="Desactivar (no se borra; deja de aceptarse en altas y ediciones)",
)
async def deactivate_document_type(
    session: SessionDep, code: str, actor: Deactivator
) -> DocumentTypeRead:
    return await controller.set_document_type_active(session, code, False, actor)


@router.post(
    "/{code}/activate",
    response_model=DocumentTypeRead,
    responses=error_responses(*AUTH_ERRORS, 404),
)
async def activate_document_type(
    session: SessionDep, code: str, actor: Deactivator
) -> DocumentTypeRead:
    return await controller.set_document_type_active(session, code, True, actor)
