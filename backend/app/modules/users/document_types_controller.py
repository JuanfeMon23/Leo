"""Catalogo de tipos de documento (`document_types`): lectura, gestion y la
validacion que usa el alta/edicion de usuarios y pacientes. Nunca se borra:
se desactiva (`users.document_type` referencia el `code`)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, snapshot
from app.core.exceptions import DuplicateValueError, ValidationAppError, not_found
from app.modules import audit
from app.modules.users import repository
from app.modules.users.models import DocumentType
from app.modules.users.schemas import (
    DocumentTypeCreate,
    DocumentTypeRead,
    DocumentTypeUpdate,
)

DOCUMENT_TYPE_FIELDS = ("code", "name", "sort_order", "is_active")
_SUBJECT = "El tipo de documento"


async def list_document_types(
    session: AsyncSession, active: bool | None
) -> list[DocumentTypeRead]:
    rows = await session.scalars(repository.document_types_statement(active))
    return [DocumentTypeRead.model_validate(row) for row in rows]


async def require_active_document_type(session: AsyncSession, code: str) -> None:
    """422 si `code` no existe en el catalogo o esta inactivo."""
    row = await repository.document_type_by_code(session, code)
    if row is None or not row.is_active:
        raise ValidationAppError(
            f"El tipo de documento «{code}» no existe o está inactivo.",
            {"document_type": code},
            code="invalid_document_type",
        )


async def _get(session: AsyncSession, code: str) -> DocumentType:
    row = await repository.document_type_by_code(session, code.strip().upper())
    if row is None:
        raise not_found(_SUBJECT, code)
    return row


async def create_document_type(
    session: AsyncSession, data: DocumentTypeCreate, actor: Actor
) -> DocumentTypeRead:
    if await repository.document_type_by_code(session, data.code) is not None:
        raise DuplicateValueError(
            entity="un tipo de documento",
            field="code",
            field_label="el código",
            value=data.code,
        )
    row = DocumentType(**data.model_dump())
    session.add(row)
    await audit.record_change(
        session,
        actor,
        "leo.document-types.create",
        "document_type",
        row,
        None,
        DOCUMENT_TYPE_FIELDS,
    )
    await session.commit()
    return DocumentTypeRead.model_validate(row)


async def update_document_type(
    session: AsyncSession, code: str, data: DocumentTypeUpdate, actor: Actor
) -> DocumentTypeRead:
    row = await _get(session, code)
    before = snapshot(row, DOCUMENT_TYPE_FIELDS)
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(row, name, value)
    await audit.record_change(
        session,
        actor,
        "leo.document-types.edit",
        "document_type",
        row,
        before,
        DOCUMENT_TYPE_FIELDS,
    )
    await session.commit()
    return DocumentTypeRead.model_validate(row)


async def set_document_type_active(
    session: AsyncSession, code: str, active: bool, actor: Actor
) -> DocumentTypeRead:
    row = await _get(session, code)
    before = snapshot(row, DOCUMENT_TYPE_FIELDS)
    row.is_active = active
    await audit.record_change(
        session,
        actor,
        "leo.document-types.deactivate",
        "document_type",
        row,
        before,
        DOCUMENT_TYPE_FIELDS,
    )
    await session.commit()
    return DocumentTypeRead.model_validate(row)
