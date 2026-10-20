"""Casos de uso de `roles`: roles por aplicacion, sus acciones y las
consultas de autorizacion (permisos efectivos, acceso a apps).

Reglas: un rol pertenece a una sola app y solo agrupa acciones de esa app
(la BD lo garantiza con FK compuesta; aqui se valida antes para dar un
mensaje claro). Nada se borra: los roles se desactivan.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, diff, snapshot
from app.core.exceptions import DuplicateValueError, ValidationAppError, not_found
from app.core.pagination import Pagination, get_or_404, paginate
from app.core.schemas import Page
from app.modules import audit
from app.modules.roles import repository
from app.modules.roles.models import Role, RoleAction
from app.modules.roles.schemas import (
    RoleActionModule,
    RoleActionRead,
    RoleActionsAdd,
    RoleCreate,
    RoleDetail,
    RoleRead,
    RoleUpdate,
)

ROLE_FIELDS = ("application_id", "slug", "name", "description", "is_active")
_ROLE = "un rol"


@dataclass(frozen=True)
class AppAccess:
    """App a la que un usuario tiene acceso (selector de la barra superior)."""

    id: UUID
    slug: str
    name: str
    base_url: str


@dataclass(frozen=True)
class RoleBrief:
    id: UUID
    application_id: UUID
    slug: str
    name: str
    is_active: bool


# --- autorizacion (interfaz publica) ---


async def effective_permissions(
    session: AsyncSession, user_id: UUID, app_id: UUID
) -> frozenset[str]:
    return frozenset(await repository.effective_permissions(session, user_id, app_id))


async def has_access(session: AsyncSession, user_id: UUID, app_id: UUID) -> bool:
    return await repository.has_access(session, user_id, app_id)


async def accessible_applications(
    session: AsyncSession, user_id: UUID
) -> list[AppAccess]:
    return [
        AppAccess(id=a.id, slug=a.slug, name=a.name, base_url=a.base_url)
        for a in await repository.accessible_applications(session, user_id)
    ]


async def roles_brief(
    session: AsyncSession, role_ids: list[UUID]
) -> dict[UUID, RoleBrief]:
    return {
        r.id: RoleBrief(r.id, r.application_id, r.slug, r.name, r.is_active)
        for r in (await repository.roles_by_id(session, role_ids)).values()
    }


# --- CRUD ---


async def list_roles(
    session: AsyncSession,
    application_id: UUID | None,
    q: str | None,
    active: bool | None,
    pagination: Pagination,
) -> Page[RoleRead]:
    stmt = repository.list_statement(application_id, q, active)
    return await paginate(session, stmt, pagination, RoleRead, Role.slug)


async def _detail(session: AsyncSession, role: Role) -> RoleDetail:
    rows = await repository.actions_with_module_of_role(session, role.id)
    return RoleDetail(
        **RoleRead.model_validate(role).model_dump(),
        actions=[
            RoleActionRead(
                id=a.id,
                tag=a.tag,
                verb=a.verb,
                name=a.name,
                description=a.description,
                is_active=a.is_active,
                module=RoleActionModule(id=m.id, slug=m.slug, name=m.name),
            )
            for a, m in rows
        ],
    )


async def get_role(session: AsyncSession, role_id: UUID) -> RoleDetail:
    return await _detail(session, await get_or_404(session, Role, role_id, _ROLE))


async def create_role(
    session: AsyncSession, data: RoleCreate, actor: Actor
) -> RoleRead:
    if not await repository.application_exists(session, data.application_id):
        raise ValidationAppError(
            f"No existe una aplicación con id '{data.application_id}'.",
            {"application_id": str(data.application_id)},
            code="invalid_reference",
        )
    if await repository.slug_exists(session, data.application_id, data.slug):
        raise DuplicateValueError(
            entity="un rol en esta aplicación",
            field="slug",
            field_label="el slug",
            value=data.slug,
        )
    role = Role(**data.model_dump())
    session.add(role)
    await audit.record_change(
        session, actor, "leo.roles.create", "role", role, None, ROLE_FIELDS
    )
    await session.commit()
    return RoleRead.model_validate(role)


async def update_role(
    session: AsyncSession, role_id: UUID, data: RoleUpdate, actor: Actor
) -> RoleRead:
    role = await get_or_404(session, Role, role_id, _ROLE)
    before = snapshot(role, ROLE_FIELDS)
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(role, name, value)
    await audit.record_change(
        session, actor, "leo.roles.edit", "role", role, before, ROLE_FIELDS
    )
    await session.commit()
    return RoleRead.model_validate(role)


async def set_role_active(
    session: AsyncSession, role_id: UUID, active: bool, actor: Actor
) -> RoleRead:
    role = await get_or_404(session, Role, role_id, _ROLE)
    before = snapshot(role, ROLE_FIELDS)
    role.is_active = active
    await audit.record_change(
        session, actor, "leo.roles.deactivate", "role", role, before, ROLE_FIELDS
    )
    await session.commit()
    return RoleRead.model_validate(role)


async def add_actions(
    session: AsyncSession, role_id: UUID, data: RoleActionsAdd, actor: Actor
) -> RoleDetail:
    role = await get_or_404(session, Role, role_id, _ROLE)
    current = await repository.actions_of_role(session, role.id)
    current_ids = {a.id for a in current}
    requested = list(dict.fromkeys(data.action_ids))
    found = await repository.actions_by_id(session, requested)
    invalid = [
        str(i)
        for i in requested
        if i not in found or found[i].application_id != role.application_id
    ]
    if invalid:
        raise ValidationAppError(
            "Algunas acciones no existen o no son de la aplicación del rol.",
            {"action_ids": invalid},
            code="invalid_reference",
        )
    new = [i for i in requested if i not in current_ids]
    for action_id in new:
        session.add(
            RoleAction(
                role_id=role.id, action_id=action_id, application_id=role.application_id
            )
        )
    await session.flush()
    if new:
        before_tags = sorted(a.tag for a in current)
        after_tags = sorted({*before_tags, *(found[i].tag for i in new)})
        await audit.record_event(
            session,
            actor.entry(
                "leo.roles.edit",
                entity_type="role",
                entity_id=str(role.id),
                changes=diff({"actions": before_tags}, {"actions": after_tags}),
            ),
        )
    await session.commit()
    return await _detail(session, role)


async def remove_action(
    session: AsyncSession, role_id: UUID, action_id: UUID, actor: Actor
) -> RoleDetail:
    role = await get_or_404(session, Role, role_id, _ROLE)
    before = [a.tag for a in await repository.actions_of_role(session, role.id)]
    if not await repository.remove_role_action(session, role.id, action_id):
        raise not_found("una acción asignada a este rol", action_id)
    after = [a.tag for a in await repository.actions_of_role(session, role.id)]
    await audit.record_event(
        session,
        actor.entry(
            "leo.roles.edit",
            entity_type="role",
            entity_id=str(role.id),
            changes=diff({"actions": before}, {"actions": after}),
        ),
    )
    await session.commit()
    return await _detail(session, role)
