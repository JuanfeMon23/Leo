"""Rutas `/api/v1/settings` (router compartido del SDK + permisos y auditoria
de Leo)."""

from typing import Any

from leo_sdk.settings_store import SettingsRouterDeps, build_settings_router

from app.core import runtime_settings
from app.core.audit import Actor, diff
from app.core.authz import require_actor
from app.modules import audit

UPDATE_TAG = "leo.settings.update"


async def audit_update(
    actor: Actor, key: str, before: Any, after: Any, reason: str
) -> None:
    """Evento `leo.settings.update` (changes before/after del valor y motivo)."""
    async with runtime_settings.store.session_factory() as session:
        await audit.record_and_commit(
            session,
            actor.entry(
                UPDATE_TAG,
                entity_type="setting",
                entity_id=key,
                changes=diff({"value": before}, {"value": after}),
                reason=reason,
            ),
        )


settings_router = build_settings_router(
    runtime_settings.store,
    SettingsRouterDeps(
        view_dep=require_actor("leo.settings.view"),
        edit_dep=require_actor("leo.settings.edit"),
        edit_security_dep=require_actor("leo.settings.edit-security"),
        audit=audit_update,
    ),
)
