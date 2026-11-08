"""Casos de uso de `roles`: roles por aplicacion, sus acciones y las
consultas de autorizacion (permisos efectivos, acceso a apps).

Reglas: un rol pertenece a una sola app y solo agrupa acciones de esa app
(la BD lo garantiza con FK compuesta; aqui se valida antes para dar un
mensaje claro). Nada se borra: los roles se desactivan.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.audit import Actor, diff, snapshot
from app.core.db.seeds.catalog import (
    LEO_APP_SLUG,
    LEO_SERVICE_GRANTABLE_ROLE_SLUGS,
)
from app.core.exceptions import DuplicateValueError, ValidationAppError, not_found
from app.core.pagination import Pagination, get_or_404, paginate
from app.core.schemas import Page
from app.modules import audit, auth
from app.modules.roles import repository
from app.modules.roles.models import Role, RoleAction, ServiceGrant
from app.modules.roles.schemas import (
    RoleActionModule,
    RoleActionRead,
    RoleActionsAdd,
    RoleCreate,
    RoleDetail,
    RoleRead,
    RoleUpdate,
    ServiceAccessGrant,
    ServiceCallerApplication,
    ServiceCallerRead,
    ServiceGrantApplication,
    ServiceGrantRead,
    ServiceGrantRole,
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
        AppAccess(
            id=action.id, slug=action.slug, name=action.name, base_url=action.base_url
        )
        for action in await repository.accessible_applications(session, user_id)
    ]


async def has_service_access(
    session: AsyncSession, caller_id: UUID, audience_id: UUID
) -> bool:
    """La app llamadora tiene >= 1 rol ACTIVO de la audiencia concedido."""
    return await repository.has_service_access(session, caller_id, audience_id)


async def service_permissions(
    session: AsyncSession, caller_id: UUID, audience_id: UUID
) -> frozenset[str]:
    """Tags activos que los roles activos concedidos a la llamadora le dan
    sobre la audiencia (calculados en vivo)."""
    return frozenset(
        await repository.service_permissions(session, caller_id, audience_id)
    )


async def active_role_brief(
    session: AsyncSession, app_slug: str, role_slug: str
) -> RoleBrief | None:
    """Rol activo (de app activa) por slugs, p. ej. `acuarius`/`paciente`."""
    role = await repository.active_role_by_slugs(session, app_slug, role_slug)
    return (
        RoleBrief(role.id, role.application_id, role.slug, role.name, role.is_active)
        if role
        else None
    )


async def roles_brief(
    session: AsyncSession, role_ids: list[UUID]
) -> dict[UUID, RoleBrief]:
    return {
        role.id: RoleBrief(
            role.id, role.application_id, role.slug, role.name, role.is_active
        )
        for role in (await repository.roles_by_id(session, role_ids)).values()
    }


# --- CRUD ---


async def list_roles(
    session: AsyncSession,
    application_id: UUID | None,
    search_text: str | None,
    active: bool | None,
    pagination: Pagination,
) -> Page[RoleRead]:
    stmt = repository.list_statement(application_id, search_text, active)
    return await paginate(session, stmt, pagination, RoleRead, Role.slug)


async def _detail(session: AsyncSession, role: Role) -> RoleDetail:
    rows = await repository.actions_with_module_of_role(session, role.id)
    return RoleDetail(
        **RoleRead.model_validate(role).model_dump(),
        actions=[
            RoleActionRead(
                id=action.id,
                tag=action.tag,
                verb=action.verb,
                name=action.name,
                description=action.description,
                is_active=action.is_active,
                module=RoleActionModule(
                    id=module.id, slug=module.slug, name=module.name
                ),
            )
            for action, module in rows
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
    current_ids = {action.id for action in current}
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
        before_tags = sorted(action.tag for action in current)
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
    before = [
        action.tag for action in await repository.actions_of_role(session, role.id)
    ]
    if not await repository.remove_role_action(session, role.id, action_id):
        raise not_found("una acción asignada a este rol", action_id)
    after = [
        action.tag for action in await repository.actions_of_role(session, role.id)
    ]
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


# --- acceso entre servicios (concesiones `service_grants`) ---

_APP = "una aplicación"


async def _service_grants(
    session: AsyncSession, caller_id: UUID
) -> list[ServiceGrantRead]:
    rows = await repository.service_grants_of_caller(session, caller_id)
    actions: dict[UUID, list[RoleActionRead]] = {}
    for role_id, action, module in await repository.actions_with_module_of_roles(
        session, [role.id for _, role, _ in rows]
    ):
        actions.setdefault(role_id, []).append(
            RoleActionRead(
                id=action.id,
                tag=action.tag,
                verb=action.verb,
                name=action.name,
                description=action.description,
                is_active=action.is_active,
                module=RoleActionModule(
                    id=module.id, slug=module.slug, name=module.name
                ),
            )
        )
    return [
        ServiceGrantRead(
            id=grant.id,
            role=ServiceGrantRole(
                id=role.id, slug=role.slug, name=role.name, is_active=role.is_active
            ),
            application=ServiceGrantApplication(
                id=app.id, slug=app.slug, name=app.name
            ),
            permissions=actions.get(role.id, []),
            created_at=grant.created_at,
        )
        for grant, role, app in rows
    ]


def _service_labels(grants: list[ServiceGrantRead]) -> list[str]:
    return sorted(f"{grant.application.slug}:{grant.role.slug}" for grant in grants)


async def _caller_or_404(session: AsyncSession, app_id: UUID) -> None:
    if await repository.get_application(session, app_id) is None:
        raise not_found(_APP, app_id)


async def list_service_access(
    session: AsyncSession, app_id: UUID
) -> list[ServiceGrantRead]:
    await _caller_or_404(session, app_id)
    return await _service_grants(session, app_id)


async def grant_service_access(
    session: AsyncSession, app_id: UUID, data: ServiceAccessGrant, actor: Actor
) -> list[ServiceGrantRead]:
    """Concede a la app `app_id` (llamadora) roles de OTRAS apps. Todo o
    nada; repetidos y ya concedidos se ignoran (idempotente)."""
    await _caller_or_404(session, app_id)
    before = await _service_grants(session, app_id)
    granted = {grant.role.id for grant in before}
    requested = list(dict.fromkeys(data.role_ids))
    found = await repository.roles_by_id(session, requested)
    missing = [str(i) for i in requested if i not in found]
    if missing:
        raise ValidationAppError(
            "Algunos roles no existen.", {"role_ids": missing}, code="invalid_reference"
        )
    new = [found[i] for i in requested if i not in granted]
    same = [str(role.id) for role in new if role.application_id == app_id]
    if same:
        raise ValidationAppError(
            "Una aplicación solo puede recibir roles de otra aplicación, no de sí "
            "misma.",
            {"role_ids": same},
            code="same_application",
        )
    apps = await repository.applications_by_id(
        session, {role.application_id for role in new}
    )
    leo_roles = [
        str(role.id)
        for role in new
        if apps[role.application_id].slug == LEO_APP_SLUG
        and role.slug not in LEO_SERVICE_GRANTABLE_ROLE_SLUGS
    ]
    if leo_roles:
        raise ValidationAppError(
            "No se concede acceso de servicio a la aplicación Leo salvo con sus "
            "roles de servicio: el resto de su API solo admite usuarios con sesión.",
            {"role_ids": leo_roles},
            code="leo_app_not_grantable",
        )
    inactive = [str(role.id) for role in new if not role.is_active]
    if inactive:
        raise ValidationAppError(
            "Algunos roles están desactivados. Actívalos antes de concederlos.",
            {"role_ids": inactive},
            code="role_inactive",
        )
    for role in new:
        session.add(
            ServiceGrant(
                caller_application_id=app_id,
                role_id=role.id,
                application_id=role.application_id,
            )
        )
    await session.flush()
    after = await _service_grants(session, app_id)
    if new:
        await audit.record_event(
            session,
            actor.entry(
                "leo.applications.grant-service-access",
                entity_type="application",
                entity_id=str(app_id),
                changes=diff(
                    {"service_roles": _service_labels(before)},
                    {"service_roles": _service_labels(after)},
                ),
            ),
        )
    await session.commit()
    return after


async def revoke_service_access(
    session: AsyncSession, app_id: UUID, role_id: UUID, actor: Actor
) -> list[ServiceGrantRead]:
    """Retira un rol concedido. Si a la llamadora ya no le queda acceso a esa
    audiencia, sus tokens de servicio vigentes se revocan en el acto."""
    await _caller_or_404(session, app_id)
    before = await _service_grants(session, app_id)
    target = next((grant for grant in before if grant.role.id == role_id), None)
    if target is None or not await repository.remove_service_grant(
        session, app_id, role_id
    ):
        raise not_found("un acceso de servicio con ese rol", role_id)
    after = await _service_grants(session, app_id)
    audience_id = target.application.id
    if not await repository.has_service_access(session, app_id, audience_id):
        await auth.revoke_service_tokens(session, app_id, audience_id, clock.now())
    await audit.record_event(
        session,
        actor.entry(
            "leo.applications.grant-service-access",
            entity_type="application",
            entity_id=str(app_id),
            changes=diff(
                {"service_roles": _service_labels(before)},
                {"service_roles": _service_labels(after)},
            ),
        ),
    )
    await session.commit()
    return after


async def list_service_callers(
    session: AsyncSession, role_id: UUID
) -> list[ServiceCallerRead]:
    await get_or_404(session, Role, role_id, _ROLE)
    return [
        ServiceCallerRead(
            id=grant.id,
            application=ServiceCallerApplication(
                id=app.id, slug=app.slug, name=app.name, is_active=app.is_active
            ),
            created_at=grant.created_at,
        )
        for grant, app in await repository.service_callers_of_role(session, role_id)
    ]
