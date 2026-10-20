"""Consultas del modulo `roles`, incluidas las de autorizacion (permisos
efectivos y acceso a apps), que cruzan tablas de `users` y `applications`
solo para LEER (las escrituras de esas tablas son de sus modulos)."""

from uuid import UUID

from sqlalchemy import Select, delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import only_active, search
from app.modules.applications.models import Action, Application, AppModule
from app.modules.roles.models import Role, RoleAction
from app.modules.users.models import UserRole


def _active_role_of_user(user_id: UUID) -> Select:
    """Roles activos de apps activas asignados a `user_id` (base de los
    permisos y del acceso)."""
    return (
        select(Role.id)
        .join(UserRole, UserRole.role_id == Role.id)
        .join(Application, Application.id == Role.application_id)
        .where(UserRole.user_id == user_id, Role.is_active, Application.is_active)
    )


async def effective_permissions(
    session: AsyncSession, user_id: UUID, app_id: UUID
) -> set[str]:
    """Union de los tags activos (accion y modulo activos) de los roles
    activos del usuario en esa app."""
    roles = _active_role_of_user(user_id).where(Role.application_id == app_id)
    stmt = (
        select(Action.tag)
        .distinct()
        .join(RoleAction, RoleAction.action_id == Action.id)
        .join(AppModule, AppModule.id == Action.module_id)
        .where(
            RoleAction.role_id.in_(roles),
            Action.is_active,
            AppModule.is_active,
        )
    )
    return set((await session.scalars(stmt)).all())


async def has_access(session: AsyncSession, user_id: UUID, app_id: UUID) -> bool:
    stmt = select(
        exists(_active_role_of_user(user_id).where(Role.application_id == app_id))
    )
    return bool(await session.scalar(stmt))


async def accessible_applications(
    session: AsyncSession, user_id: UUID
) -> list[Application]:
    app_ids = _active_role_of_user(user_id).with_only_columns(Role.application_id)
    stmt = (
        select(Application)
        .where(Application.id.in_(app_ids))
        .order_by(Application.name)
    )
    return list((await session.scalars(stmt)).all())


def list_statement(
    application_id: UUID | None, q: str | None, active: bool | None
) -> Select:
    stmt = select(Role)
    if application_id is not None:
        stmt = stmt.where(Role.application_id == application_id)
    stmt = search(stmt, q, Role.slug, Role.name, Role.description)
    return only_active(stmt, active, Role.is_active)


async def slug_exists(session: AsyncSession, app_id: UUID, slug: str) -> bool:
    found = await session.scalar(
        select(Role.id).where(Role.application_id == app_id, Role.slug == slug)
    )
    return found is not None


async def application_exists(session: AsyncSession, app_id: UUID) -> bool:
    return (
        await session.scalar(select(Application.id).where(Application.id == app_id))
        is not None
    )


async def actions_of_role(session: AsyncSession, role_id: UUID) -> list[Action]:
    stmt = (
        select(Action)
        .join(RoleAction, RoleAction.action_id == Action.id)
        .where(RoleAction.role_id == role_id)
        .order_by(Action.tag)
    )
    return list((await session.scalars(stmt)).all())


async def actions_with_module_of_role(
    session: AsyncSession, role_id: UUID
) -> list[tuple[Action, AppModule]]:
    stmt = (
        select(Action, AppModule)
        .join(RoleAction, RoleAction.action_id == Action.id)
        .join(AppModule, AppModule.id == Action.module_id)
        .where(RoleAction.role_id == role_id)
        .order_by(AppModule.slug, Action.name)
    )
    return [(a, m) for a, m in (await session.execute(stmt)).all()]


async def actions_by_id(
    session: AsyncSession, action_ids: list[UUID]
) -> dict[UUID, Action]:
    if not action_ids:
        return {}
    rows = await session.scalars(select(Action).where(Action.id.in_(action_ids)))
    return {a.id: a for a in rows}


async def remove_role_action(
    session: AsyncSession, role_id: UUID, action_id: UUID
) -> bool:
    result = await session.execute(
        delete(RoleAction).where(
            RoleAction.role_id == role_id, RoleAction.action_id == action_id
        )
    )
    return result.rowcount > 0


async def roles_by_id(session: AsyncSession, role_ids: list[UUID]) -> dict[UUID, Role]:
    if not role_ids:
        return {}
    rows = await session.scalars(select(Role).where(Role.id.in_(role_ids)))
    return {r.id: r for r in rows}
