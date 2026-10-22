"""Interfaz publica del modulo `auth` (usar `from app.modules import auth`).

- `auth_router`: rutas `/api/v1/auth`.
- `resolve_principal(request, session)`: hook de `core.authz` (cookie SSO +
  DPoP); lo conecta `app/main.py`.
- `resolve_access_token(session, app_id, token, jkt, touch=...)`: dueno de
  un access token valido de esa app (lo usa la ingesta de auditoria).
- `revoke_user_sessions(session, user_id, reason, except_session_id=None)`:
  revoca todas las sesiones de un usuario salvo una (sin commit).
- `login_limiters()`: limitadores del login (los tests los reinician).
- `service_token_limiter()`: limitador de emision de tokens de servicio.
- `revoke_service_tokens(session, caller_id, audience_id, now)`: revoca
  los tokens de servicio vigentes llamadora->audiencia (sin commit).
"""

from app.modules.auth.controller import (
    login_limiters,
    resolve_access_token,
    revoke_service_tokens,
    revoke_user_sessions,
    service_token_limiter,
)
from app.modules.auth.dependencies import resolve_principal
from app.modules.auth.router import router as auth_router

__all__ = [
    "auth_router",
    "login_limiters",
    "resolve_access_token",
    "resolve_principal",
    "revoke_service_tokens",
    "revoke_user_sessions",
    "service_token_limiter",
]
