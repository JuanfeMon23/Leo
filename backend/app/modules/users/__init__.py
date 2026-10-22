"""Interfaz publica del modulo `users` (usar `from app.modules import users`).

- `users_router`: rutas `/api/v1/users`.
- `get_identity(session, user_id) -> UserIdentity | None`.
- `check_credentials(session, login, password, ...) -> LoginCheck`: login
  (actualiza intentos, bloqueo y `last_login_at`; sin commit).
- `update_own_profile(session, user_id, data, actor) -> bool` y
  `change_own_password(session, user_id, current, new, actor)`: autogestion
  (las expone `auth` en `/auth/me/*`; sin commit).
- `ProfileUpdate`: schema del PATCH de perfil propio.
"""

from app.modules.users.controller import (
    LoginCheck,
    LoginOutcome,
    UserIdentity,
    change_own_password,
    check_credentials,
    get_identity,
    update_own_profile,
)
from app.modules.users.router import router as users_router
from app.modules.users.schemas import ProfileUpdate

__all__ = [
    "LoginCheck",
    "LoginOutcome",
    "ProfileUpdate",
    "UserIdentity",
    "change_own_password",
    "check_credentials",
    "get_identity",
    "update_own_profile",
    "users_router",
]
