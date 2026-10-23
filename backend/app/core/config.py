"""Configuracion del backend, leida desde `backend/.env`.

Es el unico punto de acceso a variables de entorno: ningun otro modulo lee
`os.environ` directamente. Todo secreto (DSN, datos del admin inicial) vive
solo en `.env` (no versionado); `.env.example` lista las claves.
"""

import ipaddress
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class Settings(BaseSettings):
    """Variables obligatorias del backend (sin defaults: si falta, falla).

    - `DATABASE_URL`: DSN de PostgreSQL (`postgresql+asyncpg://...`).
    - `LEO_FRONTEND_URL`: origen del frontend de Leo; unico origen CORS
      (con credenciales).
    - `LEO_PUBLIC_URL`: URL base publica de esta API (esquema + host +
      puerto, sin `/` final). Con ella se arma el `htu` esperado de las
      pruebas DPoP (`LEO_PUBLIC_URL + path`).
    - `LEO_COOKIE_SECURE`: `true` en produccion (HTTPS): cookie `Secure` con
      prefijo `__Host-`. `false` solo en desarrollo local por HTTP.
    - `LEO_RATE_LIMIT_BACKEND`: `memory` (por proceso; default, solo dev) o
      `postgres` (compartido entre procesos; obligatorio en produccion con
      mas de un proceso/instancia). Ver `app.core.rate_limit`.
    - `LEO_TRUSTED_PROXIES`: IP/CIDR separados por comas de los proxies
      inversos de confianza. Vacio (default): `X-Forwarded-For`/`X-Real-IP`
      se ignoran. Ver `app.core.client_ip`.
    - `MIGRATION_DATABASE_URL` (solo Alembic, ver `migrations/env.py`): DSN
      del rol `leo_migrator`; si falta, Alembic usa `DATABASE_URL`.

    Las politicas (inactividad, vida de tokens y sesion, bloqueo de login,
    limites de intentos, contrasenas, paginacion, export) YA NO son variables
    de entorno: viven en la tabla `settings` y se editan desde la pantalla
    Ajustes (ver `app.core.runtime_settings`). Las variables antiguas solo se
    leen una vez, como valor inicial (`LegacyPolicyEnv`).
    """

    model_config = _ENV

    database_url: str
    leo_frontend_url: str
    leo_public_url: str
    leo_cookie_secure: bool
    leo_rate_limit_backend: Literal["memory", "postgres"] = "memory"
    leo_trusted_proxies: str = ""

    @field_validator("leo_trusted_proxies")
    @classmethod
    def _valid_trusted_proxies(cls, value: str) -> str:
        for item in value.split(","):
            if item.strip():
                ipaddress.ip_network(item.strip(), strict=False)  # ValueError -> 422
        return value


# Variable de entorno antigua -> claves de `settings` que alimenta. Solo se usa
# en el primer arranque (`LegacyPolicyEnv`), para no cambiar el comportamiento
# de un despliegue existente al pasar las politicas a la BD.
LEGACY_POLICY_ENV: dict[str, tuple[str, ...]] = {
    "LEO_IDLE_TIMEOUT_MINUTES": ("auth.idle_timeout_minutes",),
    "LEO_ACCESS_TOKEN_MINUTES": ("auth.access_token_minutes",),
    "LEO_SESSION_MAX_HOURS": ("auth.session_max_hours",),
    "LEO_LOGIN_MAX_FAILED_ATTEMPTS": ("auth.login_max_failed_attempts",),
    "LEO_LOGIN_LOCK_MINUTES": ("auth.login_lock_minutes",),
    "LEO_LOGIN_RATE_LIMIT_PER_MINUTE": (
        "rate_limit.login_ip_per_window",
        "rate_limit.login_user_per_window",
        "rate_limit.password_ip_per_window",
        "rate_limit.password_user_per_window",
        "rate_limit.delegated_user_per_window",
    ),
    "LEO_SERVICE_TOKEN_MINUTES": ("auth.service_token_minutes",),
    "LEO_SERVICE_TOKEN_RATE_LIMIT_PER_MINUTE": ("rate_limit.service_token_per_window",),
    "LEO_PROVISION_RATE_LIMIT_PER_MINUTE": ("rate_limit.provision_per_window",),
    "LEO_DELEGATED_RATE_LIMIT_PER_MINUTE": ("rate_limit.delegated_app_per_window",),
}


class LegacyPolicyEnv(BaseSettings):
    """Variables de politica que existian antes de la tabla `settings`.

    Opcionales y NO documentadas como configuracion: si existen en el entorno
    (o en `.env`), `initial_values()` las entrega como valor inicial de las
    claves nuevas; la semilla del registro solo las usa al INSERTAR la clave,
    asi que despues la unica fuente es la BD. Un valor no numerico se ignora.
    """

    model_config = _ENV

    leo_idle_timeout_minutes: str | None = None
    leo_access_token_minutes: str | None = None
    leo_session_max_hours: str | None = None
    leo_login_max_failed_attempts: str | None = None
    leo_login_lock_minutes: str | None = None
    leo_login_rate_limit_per_minute: str | None = None
    leo_service_token_minutes: str | None = None
    leo_service_token_rate_limit_per_minute: str | None = None
    leo_provision_rate_limit_per_minute: str | None = None
    leo_delegated_rate_limit_per_minute: str | None = None

    def initial_values(self) -> dict[str, int]:
        values: dict[str, int] = {}
        for env_name, keys in LEGACY_POLICY_ENV.items():
            raw = getattr(self, env_name.lower())
            if raw is None:
                continue
            try:
                number = int(raw.strip())
            except ValueError:
                continue
            for key in keys:
                values[key] = number
        return values


class SeedSettings(BaseSettings):
    """Variables que solo usa la semilla inicial (`app.core.db.seeds`).

    Todas son opcionales aqui para que la app arranque sin ellas; la semilla
    valida las obligatorias y falla con un mensaje que nombra las que faltan
    (`app.core.db.seeds.admin.SeedConfigError`). Nunca tienen valores reales
    en el codigo.

    - `LEO_FRONTEND_URL`: URL base de la app `leo` (su frontend).
    - `LEO_ADMIN_USERNAME`, `LEO_ADMIN_EMAIL`, `LEO_ADMIN_PASSWORD`,
      `LEO_ADMIN_DOCUMENT_TYPE`, `LEO_ADMIN_DOCUMENT_NUMBER`: obligatorias.
    - `LEO_ADMIN_FIRST_NAME`, `LEO_ADMIN_LAST_NAME`: opcionales.
    """

    model_config = SettingsConfigDict(**_ENV, env_prefix="LEO_")

    frontend_url: str | None = None
    admin_username: str | None = None
    admin_email: str | None = None
    admin_password: SecretStr | None = None
    admin_document_type: str | None = None
    admin_document_number: str | None = None
    admin_first_name: str | None = None
    admin_last_name: str | None = None


@lru_cache
def get_settings() -> Settings:
    """`Settings` cacheado (se lee `.env` una sola vez)."""
    return Settings()
