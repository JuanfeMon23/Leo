"""Modulo `settings`: pantalla Ajustes (API `/api/v1/settings`).

La logica vive en el modulo compartido `leo_sdk.settings_store`; aqui solo se
conectan los permisos de Leo (`leo.settings.view|edit|edit-security`) y la
auditoria central (`leo.settings.update`). El registro de claves y el store
estan en `app.core.runtime_settings`.

- `settings_router`: rutas `/api/v1/settings` (GET lista, GET historial,
  PUT edicion).
"""

from app.modules.settings.router import settings_router

__all__ = ["settings_router"]
