"""Interfaz publica del modulo `roles` (usar `from app.modules import roles`).

- `roles_router`: rutas `/api/v1/roles`.
- `effective_permissions(session, user_id, app_id) -> frozenset[str]`: tags
  activos de los roles activos del usuario en esa app (app activa).
- `has_access(session, user_id, app_id) -> bool`: >= 1 rol activo en la app.
- `accessible_applications(session, user_id) -> list[AppAccess]`.
- `has_service_access(session, caller_id, audience_id) -> bool`: la app
  llamadora tiene >= 1 rol activo de la audiencia concedido.
- `service_permissions(session, caller_id, audience_id) -> frozenset[str]`:
  tags activos que esas concesiones le dan sobre la audiencia (en vivo).
- `service_access_router`: `/applications/{id}/service-access` (se monta bajo
  `/api/v1/applications`).
- `roles_brief(session, ids) -> {id: RoleBrief}`.
"""

from app.modules.roles.controller import (
    AppAccess,
    RoleBrief,
    accessible_applications,
    effective_permissions,
    has_access,
    has_service_access,
    roles_brief,
    service_permissions,
)
from app.modules.roles.router import router as roles_router
from app.modules.roles.router import service_access_router

__all__ = [
    "AppAccess",
    "RoleBrief",
    "accessible_applications",
    "effective_permissions",
    "has_access",
    "has_service_access",
    "roles_brief",
    "roles_router",
    "service_access_router",
    "service_permissions",
]
