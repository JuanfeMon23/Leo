"""Interfaz publica del modulo `applications`.

Otros modulos solo importan lo que se expone aqui (para evitar ciclos:
`from app.modules import applications` y uso en tiempo de ejecucion).

- `applications_router`: rutas `/api/v1/applications`.
- `authenticate_client(session, client_id, secret) -> ClientApp | None`:
  autenticador de `core.client_auth` (lo conecta `app/main.py`).
- `leo_application_id(session)`: id de la app `leo` (dogfooding).
- `get_client_info(session, client_id) -> ClientInfo | None`: datos de la
  app para `/authorize` (redirect_uris, activa).
- `get_client_info_by_id(session, app_id) -> ClientInfo | None`: igual, por id.
"""

from app.modules.applications.controller import (
    ClientInfo,
    authenticate_client,
    get_client_info,
    get_client_info_by_id,
    leo_application_id,
)
from app.modules.applications.router import router as applications_router

__all__ = [
    "ClientInfo",
    "applications_router",
    "authenticate_client",
    "get_client_info",
    "get_client_info_by_id",
    "leo_application_id",
]
