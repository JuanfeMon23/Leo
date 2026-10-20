"""Paginacion, busqueda `?q=` y filtro `?active=` reusables por los listados.

- `Pagination` (dependencia `?page=&page_size=`) + `paginate(session, stmt,
  pagination, *order_by)` -> `Page[T]` ya armado con el schema de lectura.
- `search(stmt, q, *columns)`: AND entre palabras, OR entre columnas,
  `ILIKE` con `%`/`_`/`\\` escapados.
"""

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import not_found
from app.core.schemas import Page

SEARCH_MAX_LENGTH = 100
SEARCH_MAX_TERMS = 8


@dataclass(frozen=True)
class Pagination:
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


PaginationDep = Annotated[Pagination, Depends(pagination_params)]
SearchQuery = Annotated[
    str | None,
    Query(
        max_length=SEARCH_MAX_LENGTH,
        description="Texto a buscar (sin distinguir mayusculas). Varias palabras: "
        "deben aparecer todas. Vacio = sin filtro.",
    ),
]
ActiveQuery = Annotated[
    bool | None,
    Query(description="true = solo activos, false = solo inactivos, vacio = todos."),
]


def search[StmtT: Select](stmt: StmtT, q: str | None, *columns: ColumnElement) -> StmtT:
    for term in (q or "").split()[:SEARCH_MAX_TERMS]:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(or_(*(c.ilike(pattern, escape="\\") for c in columns)))
    return stmt


def only_active[StmtT: Select](
    stmt: StmtT, active: bool | None, column: ColumnElement
) -> StmtT:
    return stmt if active is None else stmt.where(column == active)


async def paginate[ReadT: BaseModel](
    session: AsyncSession,
    stmt: Select,
    pagination: Pagination,
    read_model: type[ReadT],
    *order_by: Any,
) -> Page[ReadT]:
    """Ejecuta `stmt` (un `select(Model)` filtrado) paginado y lo devuelve
    como `Page[read_model]`. El total se cuenta sin ORDER BY ni LIMIT."""
    rows = stmt.order_by(None).with_only_columns(
        literal_column("1"), maintain_column_froms=True
    )
    total = (
        await session.execute(select(func.count()).select_from(rows.subquery()))
    ).scalar_one()
    page_stmt = (
        stmt.order_by(*order_by).offset(pagination.offset).limit(pagination.page_size)
    )
    items = (await session.execute(page_stmt)).scalars().all()
    return Page[read_model](
        items=[read_model.model_validate(item) for item in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


async def get_or_404[ModelT](
    session: AsyncSession, model: type[ModelT], entity_id: Any, subject: str
) -> ModelT:
    """Fila por id o `NotFoundError` ("No existe {subject} con id '...'.")."""
    entity = await session.get(model, entity_id, populate_existing=True)
    if entity is None:
        raise not_found(subject, entity_id)
    return entity
