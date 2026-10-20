"""Consultas del modulo `applications`."""

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.seeds.catalog import LEO_APP_SLUG
from app.core.pagination import only_active, search
from app.modules.applications.models import Action, Application, AppModule


async def get_by_slug(session: AsyncSession, slug: str) -> Application | None:
    return await session.scalar(select(Application).where(Application.slug == slug))


async def get_by_client_id(session: AsyncSession, client_id: str) -> Application | None:
    return await session.scalar(
        select(Application).where(Application.client_id == client_id)
    )


async def leo_application_id(session: AsyncSession) -> UUID:
    app_id = await session.scalar(
        select(Application.id).where(Application.slug == LEO_APP_SLUG)
    )
    if app_id is None:
        raise RuntimeError(
            "No existe la app 'leo'. Corre la semilla: uv run python -m app.core.db.seeds"
        )
    return app_id


def list_statement(q: str | None, active: bool | None) -> Select:
    stmt = select(Application)
    stmt = search(stmt, q, Application.slug, Application.name, Application.description)
    return only_active(stmt, active, Application.is_active)


async def modules_of(session: AsyncSession, app_id: UUID) -> list[AppModule]:
    rows = await session.scalars(
        select(AppModule)
        .where(AppModule.application_id == app_id)
        .order_by(AppModule.slug)
    )
    return list(rows)


async def actions_of(session: AsyncSession, app_id: UUID) -> list[Action]:
    rows = await session.scalars(
        select(Action).where(Action.application_id == app_id).order_by(Action.tag)
    )
    return list(rows)


async def get_module(
    session: AsyncSession, app_id: UUID, module_id: UUID
) -> AppModule | None:
    return await session.scalar(
        select(AppModule).where(
            AppModule.id == module_id, AppModule.application_id == app_id
        )
    )


async def module_slug_exists(session: AsyncSession, app_id: UUID, slug: str) -> bool:
    found = await session.scalar(
        select(AppModule.id).where(
            AppModule.application_id == app_id, AppModule.slug == slug
        )
    )
    return found is not None


async def get_action(
    session: AsyncSession, app_id: UUID, action_id: UUID
) -> Action | None:
    return await session.scalar(
        select(Action).where(Action.id == action_id, Action.application_id == app_id)
    )


async def tag_exists(session: AsyncSession, tag: str) -> bool:
    return await session.scalar(select(Action.id).where(Action.tag == tag)) is not None


async def action_name_exists(
    session: AsyncSession, module_id: UUID, name: str, exclude_id: UUID | None = None
) -> bool:
    stmt = select(Action.id).where(Action.module_id == module_id, Action.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Action.id != exclude_id)
    return await session.scalar(stmt) is not None
