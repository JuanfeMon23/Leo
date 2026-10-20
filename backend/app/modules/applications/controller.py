"""Casos de uso de `applications`: apps cliente, sus modulos y acciones
(tags), credenciales del cliente y sincronizacion del catalogo.

Reglas:
- `slug` de app/modulo y `verb` de accion no se renombran (el tag
  `<app>.<modulo>.<verbo>` vive en el codigo de las apps).
- Nada se borra: se desactiva/reactiva.
- La app `leo` (y sus modulos/acciones) no se desactiva ni se sincroniza
  por API: la mantiene la semilla (si no, se perderia el acceso al admin).
- `client_secret`: 256 bits aleatorios, se devuelve una sola vez, en BD
  solo su SHA-256; se compara en tiempo constante.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditEntry, diff, snapshot
from app.core.authz import EVENT_PREFIX
from app.core.client_auth import ClientApp
from app.core.crypto import constant_time_equals, new_opaque_token, sha256_hex
from app.core.db.seeds.catalog import LEO_APP_SLUG, derived_action_name
from app.core.exceptions import (
    ConflictError,
    DuplicateValueError,
    ForbiddenError,
    not_found,
)
from app.core.pagination import Pagination, get_or_404, paginate
from app.core.schemas import Page
from app.modules import audit
from app.modules.applications import repository
from app.modules.applications.models import Action, Application, AppModule
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
    ModuleWithActions,
    SecretRotated,
)

APP_FIELDS = (
    "slug",
    "name",
    "description",
    "base_url",
    "redirect_uris",
    "client_id",
    "is_active",
)
MODULE_FIELDS = ("slug", "name", "description", "is_active")
ACTION_FIELDS = ("tag", "verb", "name", "description", "is_active")

# Hash con el que se compara cuando el client_id no existe: el tiempo de
# respuesta no revela si el cliente existe.
_DUMMY_SECRET_HASH = sha256_hex("leo-client-inexistente")

_APP = "una aplicación"
_MODULE = "un módulo"
_ACTION = "una acción"


class LeoAppProtectedError(ConflictError):
    code = "leo_app_protected"

    def __init__(self) -> None:
        super().__init__(
            "La aplicación Leo, sus módulos y acciones no se desactivan ni se "
            "sincronizan por API: los mantiene la semilla (sin ellos se perdería "
            "el acceso a la administración)."
        )


class EventActionReadOnlyError(ConflictError):
    code = "event_action_readonly"

    def __init__(self, tag: str) -> None:
        super().__init__(
            f"«{tag}» es una acción de evento (solo se audita): no se puede editar.",
            {"tag": tag},
        )


def _duplicate_action_name(name: str) -> DuplicateValueError:
    return DuplicateValueError(
        entity="una acción en este módulo",
        field="name",
        field_label="el nombre",
        value=name,
    )


# --- autenticacion de clientes (hook de core.client_auth) ---


async def authenticate_client(
    session: AsyncSession, client_id: str, client_secret: str
) -> ClientApp | None:
    app = await repository.get_by_client_id(session, client_id)
    expected = app.client_secret_hash if app else _DUMMY_SECRET_HASH
    matches = constant_time_equals(sha256_hex(client_secret), expected)
    if app is None or not matches or not app.is_active:
        return None
    return ClientApp(id=app.id, slug=app.slug, client_id=app.client_id)


@dataclass(frozen=True)
class ClientInfo:
    """Datos publicos de una app para `/authorize` (sin secretos)."""

    id: UUID
    slug: str
    name: str
    client_id: str
    base_url: str
    redirect_uris: tuple[str, ...]
    is_active: bool


async def get_client_info(session: AsyncSession, client_id: str) -> ClientInfo | None:
    return _client_info(await repository.get_by_client_id(session, client_id))


async def get_client_info_by_id(
    session: AsyncSession, app_id: UUID
) -> ClientInfo | None:
    return _client_info(await session.get(Application, app_id, populate_existing=True))


def _client_info(app: Application | None) -> ClientInfo | None:
    if app is None:
        return None
    return ClientInfo(
        id=app.id,
        slug=app.slug,
        name=app.name,
        client_id=app.client_id,
        base_url=app.base_url,
        redirect_uris=tuple(app.redirect_uris),
        is_active=app.is_active,
    )


async def leo_application_id(session: AsyncSession) -> UUID:
    return await repository.leo_application_id(session)


# --- aplicaciones ---


async def list_applications(
    session: AsyncSession, q: str | None, active: bool | None, pagination: Pagination
) -> Page[ApplicationRead]:
    stmt = repository.list_statement(q, active)
    return await paginate(session, stmt, pagination, ApplicationRead, Application.slug)


async def get_application(session: AsyncSession, app_id: UUID) -> ApplicationDetail:
    app = await get_or_404(session, Application, app_id, _APP)
    modules = await repository.modules_of(session, app.id)
    actions = await repository.actions_of(session, app.id)
    by_module: dict[UUID, list[ActionRead]] = {}
    for action in actions:
        by_module.setdefault(action.module_id, []).append(
            ActionRead.model_validate(action)
        )
    return ApplicationDetail(
        **ApplicationRead.model_validate(app).model_dump(),
        modules=[
            ModuleWithActions(
                **ModuleRead.model_validate(m).model_dump(),
                actions=by_module.get(m.id, []),
            )
            for m in modules
        ],
    )


async def create_application(
    session: AsyncSession, data: ApplicationCreate, actor: Actor
) -> ApplicationCreated:
    if await repository.get_by_slug(
        session, data.slug
    ) or await repository.get_by_client_id(session, data.slug):
        raise DuplicateValueError(
            entity=_APP, field="slug", field_label="el slug", value=data.slug
        )
    secret = new_opaque_token()
    app = Application(
        **data.model_dump(), client_id=data.slug, client_secret_hash=secret.hash
    )
    session.add(app)
    await session.flush()
    await session.refresh(app)
    await audit.record_event(
        session,
        actor.entry(
            "leo.applications.create",
            entity_type="application",
            entity_id=str(app.id),
            changes=diff(None, snapshot(app, APP_FIELDS)),
        ),
    )
    await session.commit()
    return ApplicationCreated(
        application=ApplicationRead.model_validate(app), client_secret=secret.value
    )


async def update_application(
    session: AsyncSession, app_id: UUID, data: ApplicationUpdate, actor: Actor
) -> ApplicationRead:
    app = await get_or_404(session, Application, app_id, _APP)
    before = snapshot(app, APP_FIELDS)
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(app, name, value)
    await audit.record_change(
        session, actor, "leo.applications.edit", "application", app, before, APP_FIELDS
    )
    await session.commit()
    return ApplicationRead.model_validate(app)


async def set_application_active(
    session: AsyncSession, app_id: UUID, active: bool, actor: Actor
) -> ApplicationRead:
    app = await get_or_404(session, Application, app_id, _APP)
    if app.slug == LEO_APP_SLUG and not active:
        raise LeoAppProtectedError()
    before = snapshot(app, APP_FIELDS)
    app.is_active = active
    await audit.record_change(
        session,
        actor,
        "leo.applications.deactivate",
        "application",
        app,
        before,
        APP_FIELDS,
    )
    await session.commit()
    return ApplicationRead.model_validate(app)


async def rotate_secret(
    session: AsyncSession, app_id: UUID, actor: Actor
) -> SecretRotated:
    app = await get_or_404(session, Application, app_id, _APP)
    secret = new_opaque_token()
    app.client_secret_hash = secret.hash
    await session.flush()
    await audit.record_event(
        session,
        actor.entry(
            "leo.applications.rotate-secret",
            entity_type="application",
            entity_id=str(app.id),
            reason="Se regeneró el client_secret.",
        ),
    )
    await session.commit()
    return SecretRotated(client_id=app.client_id, client_secret=secret.value)


# --- modulos ---


async def create_module(
    session: AsyncSession, app_id: UUID, data: ModuleCreate, actor: Actor
) -> ModuleRead:
    app = await get_or_404(session, Application, app_id, _APP)
    if await repository.module_slug_exists(session, app.id, data.slug):
        raise DuplicateValueError(
            entity=_MODULE, field="slug", field_label="el slug", value=data.slug
        )
    module = AppModule(application_id=app.id, **data.model_dump())
    session.add(module)
    await session.flush()
    await session.refresh(module)
    await audit.record_event(
        session,
        actor.entry(
            "leo.applications.create",
            entity_type="app_module",
            entity_id=str(module.id),
            changes=diff(None, snapshot(module, MODULE_FIELDS)),
        ),
    )
    await session.commit()
    return ModuleRead.model_validate(module)


async def _module_of(session: AsyncSession, app_id: UUID, module_id: UUID) -> AppModule:
    module = await repository.get_module(session, app_id, module_id)
    if module is None:
        raise not_found(_MODULE, module_id)
    return module


async def update_module(
    session: AsyncSession,
    app_id: UUID,
    module_id: UUID,
    data: ModuleUpdate,
    actor: Actor,
) -> ModuleRead:
    module = await _module_of(session, app_id, module_id)
    before = snapshot(module, MODULE_FIELDS)
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(module, name, value)
    await audit.record_change(
        session,
        actor,
        "leo.applications.edit",
        "app_module",
        module,
        before,
        MODULE_FIELDS,
    )
    await session.commit()
    return ModuleRead.model_validate(module)


async def set_module_active(
    session: AsyncSession, app_id: UUID, module_id: UUID, active: bool, actor: Actor
) -> ModuleRead:
    app = await get_or_404(session, Application, app_id, _APP)
    if app.slug == LEO_APP_SLUG and not active:
        raise LeoAppProtectedError()
    module = await _module_of(session, app_id, module_id)
    before = snapshot(module, MODULE_FIELDS)
    module.is_active = active
    await audit.record_change(
        session,
        actor,
        "leo.applications.deactivate",
        "app_module",
        module,
        before,
        MODULE_FIELDS,
    )
    await session.commit()
    return ModuleRead.model_validate(module)


# --- acciones ---


async def create_action(
    session: AsyncSession,
    app_id: UUID,
    module_id: UUID,
    data: ActionCreate,
    actor: Actor,
) -> ActionRead:
    app = await get_or_404(session, Application, app_id, _APP)
    module = await _module_of(session, app_id, module_id)
    tag = f"{app.slug}.{module.slug}.{data.verb}"
    if await repository.tag_exists(session, tag):
        raise DuplicateValueError(
            entity=_ACTION, field="tag", field_label="el tag", value=tag
        )
    if await repository.action_name_exists(session, module.id, data.name):
        raise _duplicate_action_name(data.name)
    action = Action(
        application_id=app.id,
        module_id=module.id,
        verb=data.verb,
        tag=tag,
        name=data.name,
        description=data.description,
    )
    session.add(action)
    await session.flush()
    await session.refresh(action)
    await audit.record_event(
        session,
        actor.entry(
            "leo.applications.create",
            entity_type="action",
            entity_id=str(action.id),
            changes=diff(None, snapshot(action, ACTION_FIELDS)),
        ),
    )
    await session.commit()
    return ActionRead.model_validate(action)


async def _action_of(session: AsyncSession, app_id: UUID, action_id: UUID) -> Action:
    action = await repository.get_action(session, app_id, action_id)
    if action is None:
        raise not_found(_ACTION, action_id)
    return action


async def update_action(
    session: AsyncSession,
    app_id: UUID,
    action_id: UUID,
    data: ActionUpdate,
    actor: Actor,
) -> ActionRead:
    action = await _action_of(session, app_id, action_id)
    if (action.description or "").startswith(EVENT_PREFIX):
        raise EventActionReadOnlyError(action.tag)
    changes = data.model_dump(exclude_unset=True)
    new_name = changes.get("name")
    if new_name is not None and await repository.action_name_exists(
        session, action.module_id, new_name, exclude_id=action.id
    ):
        raise _duplicate_action_name(new_name)
    before = snapshot(action, ACTION_FIELDS)
    for name, value in changes.items():
        setattr(action, name, value)
    await audit.record_change(
        session, actor, "leo.applications.edit", "action", action, before, ACTION_FIELDS
    )
    await session.commit()
    return ActionRead.model_validate(action)


async def set_action_active(
    session: AsyncSession, app_id: UUID, action_id: UUID, active: bool, actor: Actor
) -> ActionRead:
    app = await get_or_404(session, Application, app_id, _APP)
    if app.slug == LEO_APP_SLUG and not active:
        raise LeoAppProtectedError()
    action = await _action_of(session, app_id, action_id)
    before = snapshot(action, ACTION_FIELDS)
    action.is_active = active
    await audit.record_change(
        session,
        actor,
        "leo.applications.deactivate",
        "action",
        action,
        before,
        ACTION_FIELDS,
    )
    await session.commit()
    return ActionRead.model_validate(action)


# --- sincronizacion del catalogo (la app publica sus tags) ---


async def sync_catalog(
    session: AsyncSession,
    slug: str,
    client: ClientApp,
    catalog: CatalogSync,
    request_id: str | None,
) -> CatalogSyncResult:
    """Registra/actualiza los modulos y acciones que la app declara en su
    codigo. Idempotente; solo desactiva lo ausente con `deactivate_missing`.
    No reactiva lo que un admin desactivo.

    Nombre legible de las acciones (`CatalogAction.name`, opcional): al crear
    se usa el declarado o, si falta, el derivado del verbo
    (`derived_action_name`). En una accion existente solo se reemplaza si el
    nombre guardado aun es el derivado (no pisa lo que un admin edito). Un
    nombre repetido dentro del modulo da 409 `duplicate` (`details.name`)."""
    if client.slug != slug:
        raise ForbiddenError(
            "Una aplicación solo puede sincronizar su propio catálogo.",
            {"slug": slug},
            code="client_mismatch",
        )
    app = await repository.get_by_slug(session, slug)
    if app is None:
        raise not_found(_APP, slug)
    if app.slug == LEO_APP_SLUG:
        raise LeoAppProtectedError()

    result = CatalogSyncResult()
    modules = {m.slug: m for m in await repository.modules_of(session, app.id)}
    actions = {a.tag: a for a in await repository.actions_of(session, app.id)}
    declared_tags: set[str] = set()
    taken_names = {(a.module_id, a.name) for a in actions.values()}

    for declared in catalog.modules:
        module = modules.get(declared.slug)
        if module is None:
            module = AppModule(
                application_id=app.id,
                slug=declared.slug,
                name=declared.name,
                description=declared.description,
            )
            session.add(module)
            await session.flush()
            modules[module.slug] = module
            result.created_modules.append(module.slug)
        elif (module.name, module.description) != (declared.name, declared.description):
            module.name, module.description = declared.name, declared.description
            result.updated_modules.append(module.slug)

        for declared_action in declared.actions:
            tag = f"{app.slug}.{module.slug}.{declared_action.verb}"
            declared_tags.add(tag)
            action = actions.get(tag)
            if action is None:
                name = declared_action.name or derived_action_name(declared_action.verb)
                if (module.id, name) in taken_names:
                    raise _duplicate_action_name(name)
                taken_names.add((module.id, name))
                session.add(
                    Action(
                        application_id=app.id,
                        module_id=module.id,
                        verb=declared_action.verb,
                        tag=tag,
                        name=name,
                        description=declared_action.description,
                    )
                )
                result.created_actions.append(tag)
                continue
            changed = False
            new_name = declared_action.name
            if (
                new_name is not None
                and new_name != action.name
                and action.name == derived_action_name(action.verb)
            ):
                if (module.id, new_name) in taken_names:
                    raise _duplicate_action_name(new_name)
                taken_names.discard((module.id, action.name))
                taken_names.add((module.id, new_name))
                action.name = new_name
                changed = True
            if action.description != declared_action.description:
                action.description = declared_action.description
                changed = True
            if changed:
                result.updated_actions.append(tag)

    if catalog.deactivate_missing:
        declared_modules = {m.slug for m in catalog.modules}
        for module in modules.values():
            if module.slug not in declared_modules and module.is_active:
                module.is_active = False
                result.deactivated_modules.append(module.slug)
        for tag, action in actions.items():
            if tag not in declared_tags and action.is_active:
                action.is_active = False
                result.deactivated_actions.append(tag)

    await session.flush()
    summary = result.model_dump()
    if any(summary.values()):
        await audit.record_event(
            session,
            AuditEntry(
                action_tag="leo.applications.sync-catalog",
                entity_type="application",
                entity_id=str(app.id),
                changes={
                    k: {"before": None, "after": v} for k, v in summary.items() if v
                },
                reason=f"Sincronización del catálogo por el cliente «{client.client_id}».",
                request_id=request_id,
            ),
        )
    await session.commit()
    return result
