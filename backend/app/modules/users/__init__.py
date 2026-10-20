"""Interfaz publica del modulo `users` (usar `from app.modules import users`).

- `users_router`: rutas `/api/v1/users`.
- `get_identity(session, user_id) -> UserIdentity | None`.
- `check_credentials(session, login, password, ...) -> LoginCheck`: login
  (actualiza intentos, bloqueo y `last_login_at`; sin commit).
"""

from app.modules.users.controller import (
    LoginCheck,
    LoginOutcome,
    UserIdentity,
    check_credentials,
    get_identity,
)
from app.modules.users.router import router as users_router

__all__ = [
    "LoginCheck",
    "LoginOutcome",
    "UserIdentity",
    "check_credentials",
    "get_identity",
    "users_router",
]
