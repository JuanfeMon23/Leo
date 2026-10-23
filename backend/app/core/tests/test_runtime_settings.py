"""Registro de ajustes de Leo, valores iniciales heredados del entorno,
politica de contrasenas con piso de codigo y limitadores con regla por
llamada."""

import pytest
from sqlalchemy import text

from app.core import runtime_settings
from app.core.config import LEGACY_POLICY_ENV, LegacyPolicyEnv
from app.core.rate_limit import SlidingWindowLimiter
from app.core.runtime_settings import LEO_SETTINGS
from app.core.security.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PasswordPolicy,
    password_weaknesses,
)

# clave -> (tipo, defecto, min, max, unidad, grupo, seguridad)
EXPECTED = {
    "auth.idle_timeout_minutes": ("int", 30, 5, 120, "minutes", "auth", False),
    "auth.access_token_minutes": ("int", 15, 5, 60, "minutes", "auth", False),
    "auth.session_max_hours": ("int", 12, 1, 24, "hours", "auth", False),
    "auth.login_max_failed_attempts": ("int", 5, 3, 20, "count", "auth", True),
    "auth.login_lock_minutes": ("int", 1, 1, 1440, "minutes", "auth", True),
    "auth.service_token_minutes": ("int", 10, 1, 60, "minutes", "auth", True),
    "rate_limit.window_seconds": ("int", 60, 10, 3600, "seconds", "rate_limit", False),
    "rate_limit.login_ip_per_window": ("int", 10, 3, 60, "count", "rate_limit", False),
    "rate_limit.login_user_per_window": (
        "int",
        10,
        3,
        60,
        "count",
        "rate_limit",
        False,
    ),
    "rate_limit.password_ip_per_window": (
        "int",
        10,
        3,
        60,
        "count",
        "rate_limit",
        False,
    ),
    "rate_limit.password_user_per_window": (
        "int",
        10,
        3,
        60,
        "count",
        "rate_limit",
        False,
    ),
    "rate_limit.delegated_user_per_window": (
        "int",
        120,
        10,
        1000,
        "count",
        "rate_limit",
        False,
    ),
    "rate_limit.delegated_app_per_window": (
        "int",
        120,
        10,
        1000,
        "count",
        "rate_limit",
        False,
    ),
    "rate_limit.service_token_per_window": (
        "int",
        30,
        5,
        300,
        "count",
        "rate_limit",
        False,
    ),
    "rate_limit.provision_per_window": (
        "int",
        20,
        1,
        300,
        "count",
        "rate_limit",
        False,
    ),
    "rate_limit.public_policy_per_window": (
        "int",
        60,
        10,
        600,
        "count",
        "rate_limit",
        False,
    ),
    "password.min_length": ("int", 12, 12, 32, "count", "password", True),
    "password.require_lowercase": ("bool", True, None, None, None, "password", True),
    "password.require_uppercase": ("bool", True, None, None, None, "password", True),
    "password.require_digit": ("bool", True, None, None, None, "password", True),
    "password.require_symbol": ("bool", True, None, None, None, "password", True),
    "pagination.max_page_size": ("int", 200, 50, 500, "count", "pagination", False),
    "audit.export_max_rows": ("int", 50000, 1000, 200000, "count", "audit", False),
}


def test_registro_con_las_claves_rangos_y_grupos_acordados():
    assert set(LEO_SETTINGS.keys()) == set(EXPECTED)
    for key, expected in EXPECTED.items():
        d = LEO_SETTINGS.get(key)
        got = (d.type, d.default, d.min, d.max, d.unit, d.group, d.requires_security)
        assert got == expected, key
        assert d.description


def test_cada_variable_heredada_apunta_a_claves_del_registro():
    for keys in LEGACY_POLICY_ENV.values():
        assert all(k in LEO_SETTINGS for k in keys)
    # LEO_LOGIN_RATE_LIMIT_PER_MINUTE alimentaba 5 limites: ahora son 5 claves.
    assert len(LEGACY_POLICY_ENV["LEO_LOGIN_RATE_LIMIT_PER_MINUTE"]) == 5


def test_variables_antiguas_se_traducen_a_valores_iniciales(monkeypatch):
    for name in LEGACY_POLICY_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LEO_LOGIN_RATE_LIMIT_PER_MINUTE", "7")
    monkeypatch.setenv("LEO_SESSION_MAX_HOURS", "8")
    monkeypatch.setenv("LEO_LOGIN_LOCK_MINUTES", "no-es-numero")
    initial = LegacyPolicyEnv(_env_file=None).initial_values()
    assert initial == {
        "rate_limit.login_ip_per_window": 7,
        "rate_limit.login_user_per_window": 7,
        "rate_limit.password_ip_per_window": 7,
        "rate_limit.password_user_per_window": 7,
        "rate_limit.delegated_user_per_window": 7,
        "auth.session_max_hours": 8,
    }


async def test_primer_arranque_usa_el_entorno_como_valor_inicial_y_luego_la_bd(
    session, monkeypatch
):
    for name in LEGACY_POLICY_ENV:
        monkeypatch.delenv(name, raising=False)
    await session.execute(
        text("DELETE FROM settings WHERE key = 'auth.login_lock_minutes'")
    )
    monkeypatch.setenv("LEO_LOGIN_LOCK_MINUTES", "7")
    await runtime_settings.sync_on_startup()
    assert await runtime_settings.get("auth.login_lock_minutes") == 7
    # Un segundo arranque con otra variable NO pisa el valor vigente.
    monkeypatch.setenv("LEO_LOGIN_LOCK_MINUTES", "9")
    await runtime_settings.sync_on_startup()
    assert await runtime_settings.get("auth.login_lock_minutes") == 7


async def test_valor_heredado_fuera_de_rango_cae_al_default(session, monkeypatch):
    for name in LEGACY_POLICY_ENV:
        monkeypatch.delenv(name, raising=False)
    await session.execute(
        text("DELETE FROM settings WHERE key = 'auth.session_max_hours'")
    )
    monkeypatch.setenv("LEO_SESSION_MAX_HOURS", "999")
    await runtime_settings.sync_on_startup()
    assert await runtime_settings.get("auth.session_max_hours") == 12


@pytest.mark.parametrize("minimum", [0, 1, 11, -5])
def test_politica_de_contrasena_no_baja_del_piso(minimum):
    policy = PasswordPolicy(min_length=minimum)
    assert policy.min_length == MIN_PASSWORD_LENGTH
    assert password_weaknesses("Ab-1xyz-9", policy=policy)


def test_politica_de_contrasena_techo_y_clases():
    assert PasswordPolicy(min_length=500).min_length == MAX_PASSWORD_LENGTH
    relaxed = PasswordPolicy(require_symbol=False, require_digit=False)
    assert password_weaknesses("ClaveSegurisima", policy=relaxed) == []
    assert password_weaknesses("ClaveSegurisima") != []
    strict = PasswordPolicy(min_length=20)
    assert "debe tener entre 20 y 128 caracteres" in password_weaknesses(
        "Clave-Segura-2026!", policy=strict
    )


async def test_limitador_acepta_limite_y_ventana_por_llamada():
    limiter = SlidingWindowLimiter(bucket="t")
    with pytest.raises(ValueError):
        await limiter.check_and_hit("k")
    rule = {"limit": 2, "window_seconds": 60}
    assert await limiter.check_and_hit("k", **rule) == 0
    assert await limiter.check_and_hit("k", **rule) == 0
    assert await limiter.check_and_hit("k", **rule) > 0
    # Subir el limite en la siguiente llamada aplica de inmediato.
    assert await limiter.check_and_hit("k", limit=3, window_seconds=60) == 0
    assert await limiter.retry_after("k", limit=4, window_seconds=60) == 0
    assert await limiter.retry_after("k", limit=3, window_seconds=60) > 0
