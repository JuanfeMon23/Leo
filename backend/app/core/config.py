"""Configuracion del backend, leida desde `backend/.env`.

Es el unico punto de acceso a variables de entorno: ningun otro modulo lee
`os.environ` directamente. Todo secreto (DSN, datos del admin inicial) vive
solo en `.env` (no versionado); `.env.example` lista las claves.
"""

from functools import lru_cache

from pydantic import Field, SecretStr
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
    - `LEO_IDLE_TIMEOUT_MINUTES`: inactividad maxima de una sesion (30).
    - `LEO_ACCESS_TOKEN_MINUTES`: vida del access token de las apps (15).
    - `LEO_SESSION_MAX_HOURS`: vida absoluta maxima de una sesion SSO.
    - `LEO_COOKIE_SECURE`: `true` en produccion (HTTPS): cookie `Secure` con
      prefijo `__Host-`. `false` solo en desarrollo local por HTTP.
    - `LEO_LOGIN_MAX_FAILED_ATTEMPTS` / `LEO_LOGIN_LOCK_MINUTES`: bloqueo
      temporal de un usuario tras N contrasenas incorrectas seguidas.
    - `LEO_LOGIN_RATE_LIMIT_PER_MINUTE`: intentos de login por minuto, por IP
      y por usuario.
    - `LEO_SERVICE_TOKEN_MINUTES`: vida del token de servicio (client
      credentials), 10 por defecto y tope 60 (la BD lo exige).
    - `LEO_SERVICE_TOKEN_RATE_LIMIT_PER_MINUTE`: emisiones de tokens de
      servicio por minuto y por cliente (30 por defecto).
    """

    model_config = _ENV

    database_url: str
    leo_frontend_url: str
    leo_public_url: str
    leo_idle_timeout_minutes: int = Field(gt=0)
    leo_access_token_minutes: int = Field(gt=0)
    leo_session_max_hours: int = Field(gt=0)
    leo_cookie_secure: bool
    leo_login_max_failed_attempts: int = Field(gt=0)
    leo_login_lock_minutes: int = Field(gt=0)
    leo_login_rate_limit_per_minute: int = Field(gt=0)
    leo_service_token_minutes: int = Field(default=10, gt=0, le=60)
    leo_service_token_rate_limit_per_minute: int = Field(default=30, gt=0)


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
