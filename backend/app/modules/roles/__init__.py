"""Interfaz publica del modulo `roles` (usar `from app.modules import roles`).

- `roles_router`: rutas `/api/v1/roles`.
- `effective_permissions(session, user_id, app_id) -> frozenset[str]`: tags
  activos de los roles activos del usuario en esa app (app activa).
- `has_access(session, user_id, app_id) -> bool`: >= 1 rol activo en la app.
- `accessible_applications(session, user_id) -> list[AppAccess]`.
- `roles_brief(session, ids) -> {id: RoleBrief}`.
"""

from app.modules.roles.controller import (
    AppAccess,
    RoleBrief,
    accessible_applications,
    effective_permissions,
    has_access,
    roles_brief,
)
from app.modules.roles.router import router as roles_router

__all__ = [
    "AppAccess",
    "RoleBrief",
    "accessible_applications",
    "effective_permissions",
    "has_access",
    "roles_brief",
    "roles_router",
]
