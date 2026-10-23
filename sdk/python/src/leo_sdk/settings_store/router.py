"""Router FastAPI reutilizable de la pantalla Ajustes.

```python
router = build_settings_router(store, SettingsRouterDeps(
    view_dep=require_actor("miapp.settings.view"),
    edit_dep=require_actor("miapp.settings.edit"),
    edit_security_dep=require_actor("miapp.settings.edit-security"),
    audit=my_audit,   # async (actor, key, before, after, reason)
))
app.include_router(router, prefix="/api/v1/settings")
```

Rutas (relativas al prefijo):
- `GET ""`: ajustes agrupados por `group`.
- `GET "/{key}/history?page=&page_size="`: historial de una clave.
- `PUT "/{key}"` `{value, reason, expected_version}`: edita. Editar una clave
  con `requires_security_permission` exige ademas `edit_security_dep`.

Los permisos los inyecta la app: cada `*_dep` es un `Depends(...)` (o un
callable) que autentica/autoriza y devuelve el "actor" (cualquier objeto con
`user_id`, `username` y, opcionalmente, `meta.request_id`; ver `actor_of`).
Errores: `{code, message, details}` en espanol.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi import params as fastapi_params
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from leo_sdk.settings_store.errors import SettingNotFoundError, SettingsError
from leo_sdk.settings_store.store import (
    HistoryEntry,
    SettingsActor,
    SettingsStore,
    SettingView,
)

AuditCallback = Callable[[Any, str, Any, Any, str], Awaitable[None]]


def default_actor(raw: Any) -> SettingsActor:
    """`SettingsActor` de lo que devuelve la dependencia de permiso."""
    if isinstance(raw, SettingsActor):
        return raw
    meta = getattr(raw, "meta", None)
    return SettingsActor(
        user_id=getattr(raw, "user_id", None),
        username=getattr(raw, "username", None),
        request_id=getattr(meta, "request_id", None)
        or getattr(raw, "request_id", None),
    )


@dataclass
class SettingsRouterDeps:
    view_dep: Any
    edit_dep: Any
    edit_security_dep: Any
    audit: AuditCallback | None = None
    actor_of: Callable[[Any], SettingsActor] = field(default=default_actor)


class SettingOut(BaseModel):
    key: str
    type: str
    value: Any
    default: Any
    min: int | float | None
    max: int | float | None
    unit: str | None
    description: str
    version: int
    requires_security_permission: bool
    updated_at: datetime | None
    updated_by: UUID | None
    updated_by_username: str | None


class SettingGroupOut(BaseModel):
    group: str
    settings: list[SettingOut]


class SettingsOut(BaseModel):
    groups: list[SettingGroupOut]


class SettingUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any = Field(...)
    # Se valida en el store (3..500) para responder `reason_required`.
    reason: str | None = None
    expected_version: int = Field(ge=0)


class SettingHistoryOut(BaseModel):
    id: UUID
    setting_key: str
    old_value: Any
    new_value: Any
    version_after: int
    changed_by: UUID | None
    changed_by_username: str | None
    changed_at: datetime
    reason: str
    request_id: str | None


class SettingHistoryPageOut(BaseModel):
    items: list[SettingHistoryOut]
    page: int
    page_size: int
    total: int


def _setting_out(view: SettingView) -> SettingOut:
    return SettingOut(
        key=view.key,
        type=view.type,
        value=view.value,
        default=view.default,
        min=view.min,
        max=view.max,
        unit=view.unit,
        description=view.description,
        version=view.version,
        requires_security_permission=view.requires_security_permission,
        updated_at=view.updated_at,
        updated_by=view.updated_by,
        updated_by_username=view.updated_by_username,
    )


def _history_out(entry: HistoryEntry) -> SettingHistoryOut:
    return SettingHistoryOut(**entry.__dict__)


def _error(exc: SettingsError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.body())


def _as_dependency(dep: Any) -> fastapi_params.Depends:
    return dep if isinstance(dep, fastapi_params.Depends) else Depends(dep)


def build_settings_router(store: SettingsStore, deps: SettingsRouterDeps) -> APIRouter:
    router = APIRouter(tags=["settings"])
    view_dep = _as_dependency(deps.view_dep)
    edit_dep = _as_dependency(deps.edit_dep)
    security_dep = _as_dependency(deps.edit_security_dep)

    @router.get("", response_model=SettingsOut, summary="Ajustes agrupados")
    async def list_settings(_actor: Annotated[Any, view_dep]):
        try:
            grouped = await store.list()
        except SettingsError as exc:
            return _error(exc)
        return SettingsOut(
            groups=[
                SettingGroupOut(group=group, settings=[_setting_out(v) for v in views])
                for group, views in grouped.items()
            ]
        )

    @router.get(
        "/{key}/history",
        response_model=SettingHistoryPageOut,
        summary="Historial de cambios de un ajuste",
    )
    async def setting_history(
        key: str,
        _actor: Annotated[Any, view_dep],
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        if key not in store.registry:
            return _error(SettingNotFoundError(key))
        try:
            result = await store.history(key, page, page_size)
        except SettingsError as exc:
            return _error(exc)
        return SettingHistoryPageOut(
            items=[_history_out(e) for e in result.items],
            page=result.page,
            page_size=result.page_size,
            total=result.total,
        )

    async def apply(raw_actor: Any, key: str, body: SettingUpdateIn):
        try:
            change = await store.update(
                key,
                body.value,
                body.reason or "",
                deps.actor_of(raw_actor),
                body.expected_version,
            )
            if deps.audit is not None:
                await deps.audit(
                    raw_actor, key, change.before, change.after, change.reason
                )
        except SettingsError as exc:
            return _error(exc)
        return _setting_out(change.view)

    def put_route(definition_key: str, requires_security: bool) -> None:
        # Una ruta por clave declarada: la dependencia de permiso depende de si
        # la clave exige seguridad, y FastAPI las resuelve antes del handler.
        # Se registra con su path literal (tiene prioridad sobre `/{key}`).
        if requires_security:

            async def put_secure(
                body: SettingUpdateIn,
                _edit: Annotated[Any, edit_dep],
                actor: Annotated[Any, security_dep],
            ):
                return await apply(actor, definition_key, body)

            handler = put_secure
        else:

            async def put_plain(body: SettingUpdateIn, actor: Annotated[Any, edit_dep]):
                return await apply(actor, definition_key, body)

            handler = put_plain
        router.add_api_route(
            f"/{definition_key}",
            handler,
            methods=["PUT"],
            response_model=SettingOut,
            summary=f"Editar {definition_key}",
            name=f"update_{definition_key}",
        )

    for definition in store.registry:
        put_route(definition.key, definition.requires_security)

    @router.put("/{key}", include_in_schema=False)
    async def put_unknown(key: str, _actor: Annotated[Any, edit_dep]):
        return _error(SettingNotFoundError(key))

    return router
