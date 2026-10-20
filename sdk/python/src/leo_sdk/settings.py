"""Configuracion del SDK, leida del entorno (y `.env`). El `client_secret`
solo se acepta por entorno; nunca va en codigo."""

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LeoSettings(BaseSettings):
    """Variables de entorno:

    - `LEO_URL`: origen del frontend de Leo (pantalla `/authorize`).
    - `LEO_API_URL`: API de Leo incluyendo `/api/v1` (p. ej.
      `http://localhost:8100/api/v1`).
    - `APP_CLIENT_ID` / `APP_CLIENT_SECRET`: credenciales de la app en Leo
      (`client_id` = slug de la app).
    - `PUBLIC_URL`: URL publica de ESTE backend (esquema + host + puerto); con
      ella se arma el `htu` esperado de las pruebas DPoP.
    - `APP_REDIRECT_URI`: `redirect_uri` registrada en Leo (por defecto
      `PUBLIC_URL + /auth/callback`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    leo_url: str = Field(validation_alias=AliasChoices("LEO_URL", "leo_url"))
    leo_api_url: str = Field(
        validation_alias=AliasChoices("LEO_API_URL", "leo_api_url")
    )
    app_client_id: str = Field(
        validation_alias=AliasChoices("APP_CLIENT_ID", "app_client_id")
    )
    app_client_secret: SecretStr = Field(
        validation_alias=AliasChoices("APP_CLIENT_SECRET", "app_client_secret")
    )
    public_url: str = Field(validation_alias=AliasChoices("PUBLIC_URL", "public_url"))
    redirect_uri: str | None = Field(
        default=None, validation_alias=AliasChoices("APP_REDIRECT_URI", "redirect_uri")
    )
    # Clave para firmar la cookie de flujo; si falta se deriva del client_secret.
    state_secret: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("APP_STATE_SECRET", "state_secret")
    )

    # Cookies (HttpOnly + SameSite=Strict siempre; Secure y prefijo __Host- si
    # `cookie_secure`).
    cookie_secure: bool = True
    access_cookie_name: str = "leo_access"
    refresh_cookie_name: str = "leo_refresh"
    flow_cookie_name: str = "leo_oauth"
    cookie_path: str = "/"

    introspection_ttl_seconds: int = Field(default=30, ge=0)
    flow_ttl_seconds: int = Field(default=600, gt=0)
    http_timeout_seconds: float = Field(default=5.0, gt=0)
    audit_queue_size: int = Field(default=1000, gt=0)

    @property
    def callback_url(self) -> str:
        return self.redirect_uri or self.public_url.rstrip("/") + "/auth/callback"

    def cookie_name(self, base: str) -> str:
        """`__Host-` exige Secure, Path=/ y sin Domain."""
        if self.cookie_secure and self.cookie_path == "/":
            return f"__Host-{base}"
        return base
