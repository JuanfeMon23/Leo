"""Ajustes editables de Leo (tabla `settings`): registro de claves + store.

Las politicas operativas (sesion, tokens, bloqueo de login, limites de
intentos, contrasenas, paginacion, export) se declaran AQUI y se leen en cada
peticion con `await get("<clave>")` (cache en proceso de ~10 s, invalidada al
instante al editar). Si la BD falla o la fila falta, se usa el default del
registro (nunca un valor fuera de rango). El modulo compartido es
`leo_sdk.settings_store`; el router vive en `app.modules.settings`.

Infraestructura (URLs, DB, cookie secure, backend del rate limit, proxies de
confianza) NO esta aqui: sigue en variables de entorno (`app.core.config`).
"""

import logging
from typing import Any

from leo_sdk.settings_store import SettingDef, SettingsRegistry, SettingsStore

from app.core.config import LegacyPolicyEnv
from app.core.database import SessionLocal
from app.core.db.settings_model import SETTINGS_MODELS
from app.core.security.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PasswordPolicy,
)

logger = logging.getLogger("leo")

CACHE_TTL_SECONDS = 10.0
# Tope duro del token de servicio: tambien lo exige un CHECK en la BD
# (`service_tokens`), asi que ni el ajuste ni el codigo lo superan.
SERVICE_TOKEN_MAX_MINUTES = 60


def _rate(key: str, default: int, minimum: int, maximum: int, what: str) -> SettingDef:
    return SettingDef(
        key,
        "int",
        default,
        what,
        min=minimum,
        max=maximum,
        unit="count",
        group="rate_limit",
    )


LEO_SETTINGS = SettingsRegistry(
    [
        SettingDef(
            "auth.idle_timeout_minutes",
            "int",
            30,
            "Minutos de inactividad tras los que se cierra la sesión.",
            min=5,
            max=120,
            unit="minutes",
            group="auth",
        ),
        SettingDef(
            "auth.access_token_minutes",
            "int",
            15,
            "Vida del access token que reciben las aplicaciones.",
            min=5,
            max=60,
            unit="minutes",
            group="auth",
        ),
        SettingDef(
            "auth.session_max_hours",
            "int",
            12,
            "Vida absoluta máxima de una sesión, con o sin actividad.",
            min=1,
            max=24,
            unit="hours",
            group="auth",
        ),
        SettingDef(
            "auth.login_max_failed_attempts",
            "int",
            5,
            "Contraseñas incorrectas seguidas antes de bloquear al usuario.",
            min=3,
            max=20,
            unit="count",
            group="auth",
            requires_security=True,
        ),
        SettingDef(
            "auth.login_lock_minutes",
            "int",
            1,
            "Minutos que dura el bloqueo temporal tras demasiados fallos.",
            min=1,
            max=1440,
            unit="minutes",
            group="auth",
            requires_security=True,
        ),
        SettingDef(
            "auth.service_token_minutes",
            "int",
            10,
            "Vida del token de servicio entre aplicaciones (tope duro: 60).",
            min=1,
            max=SERVICE_TOKEN_MAX_MINUTES,
            unit="minutes",
            group="auth",
            requires_security=True,
        ),
        SettingDef(
            "rate_limit.window_seconds",
            "int",
            60,
            "Duración de la ventana de los límites de intentos.",
            min=10,
            max=3600,
            unit="seconds",
            group="rate_limit",
        ),
        _rate(
            "rate_limit.login_ip_per_window",
            10,
            3,
            60,
            "Intentos de inicio de sesión por ventana y por IP.",
        ),
        _rate(
            "rate_limit.login_user_per_window",
            10,
            3,
            60,
            "Intentos de inicio de sesión por ventana y por usuario.",
        ),
        _rate(
            "rate_limit.password_ip_per_window",
            10,
            3,
            60,
            "Intentos de cambio de contraseña o correo por ventana y por IP.",
        ),
        _rate(
            "rate_limit.password_user_per_window",
            10,
            3,
            60,
            "Intentos de cambio de contraseña o correo por ventana y por usuario.",
        ),
        _rate(
            "rate_limit.delegated_user_per_window",
            120,
            10,
            1000,
            "Llamadas delegadas por ventana y por usuario.",
        ),
        _rate(
            "rate_limit.delegated_app_per_window",
            120,
            10,
            1000,
            "Llamadas delegadas por ventana y por aplicación llamadora.",
        ),
        _rate(
            "rate_limit.service_token_per_window",
            30,
            5,
            300,
            "Emisiones de token de servicio por ventana y por cliente.",
        ),
        _rate(
            "rate_limit.provision_per_window",
            20,
            1,
            300,
            "Altas de pacientes por ventana y por aplicación llamadora.",
        ),
        _rate(
            "rate_limit.public_policy_per_window",
            60,
            10,
            600,
            "Consultas de la política de contraseñas (pública) por ventana y por IP.",
        ),
        SettingDef(
            "password.min_length",
            "int",
            MIN_PASSWORD_LENGTH,
            "Longitud mínima de las contraseñas nuevas (el piso es 12).",
            min=MIN_PASSWORD_LENGTH,
            max=32,
            unit="count",
            group="password",
            requires_security=True,
        ),
        SettingDef(
            "password.require_lowercase",
            "bool",
            True,
            "Exigir al menos una minúscula.",
            group="password",
            requires_security=True,
        ),
        SettingDef(
            "password.require_uppercase",
            "bool",
            True,
            "Exigir al menos una mayúscula.",
            group="password",
            requires_security=True,
        ),
        SettingDef(
            "password.require_digit",
            "bool",
            True,
            "Exigir al menos un dígito.",
            group="password",
            requires_security=True,
        ),
        SettingDef(
            "password.require_symbol",
            "bool",
            True,
            "Exigir al menos un símbolo.",
            group="password",
            requires_security=True,
        ),
        SettingDef(
            "pagination.max_page_size",
            "int",
            200,
            "Máximo de filas por página en los listados.",
            min=50,
            max=500,
            unit="count",
            group="pagination",
        ),
        SettingDef(
            "audit.export_max_rows",
            "int",
            50_000,
            "Máximo de eventos en una exportación CSV de auditoría.",
            min=1000,
            max=200_000,
            unit="count",
            group="audit",
        ),
    ]
)

store = SettingsStore(
    LEO_SETTINGS, SessionLocal, SETTINGS_MODELS, cache_ttl=CACHE_TTL_SECONDS
)


async def get(key: str) -> Any:
    """Valor vigente del ajuste (con cache; nunca lanza por la BD)."""
    return await store.get(key)


async def get_many(*keys: str) -> dict[str, Any]:
    return await store.get_many(keys)


async def password_policy() -> PasswordPolicy:
    """Politica de contrasenas vigente; el piso/techo de longitud es de codigo."""
    values = await store.get_many(
        [
            "password.min_length",
            "password.require_lowercase",
            "password.require_uppercase",
            "password.require_digit",
            "password.require_symbol",
        ]
    )
    return PasswordPolicy(
        min_length=max(MIN_PASSWORD_LENGTH, min(values["password.min_length"], 32)),
        max_length=MAX_PASSWORD_LENGTH,
        require_lowercase=values["password.require_lowercase"],
        require_uppercase=values["password.require_uppercase"],
        require_digit=values["password.require_digit"],
        require_symbol=values["password.require_symbol"],
    )


async def sync_on_startup() -> None:
    """Alinea la tabla con el registro (llamar al arrancar la API). Las
    variables antiguas (`LegacyPolicyEnv`) solo fijan el valor inicial de una
    clave que aun no existe. Si la BD no responde, la app arranca igual con
    los defaults (y el fallo queda en el log)."""
    try:
        result = await store.sync_registry(LegacyPolicyEnv().initial_values())
    except Exception:
        logger.exception("No se pudo sincronizar la tabla de ajustes al arrancar.")
        return
    if result.inserted or result.updated or result.adjusted:
        logger.info(
            "Ajustes sincronizados: %d nuevos, %d con metadatos actualizados, "
            "%d valores ajustados al rango.",
            len(result.inserted),
            len(result.updated),
            len(result.adjusted),
        )
