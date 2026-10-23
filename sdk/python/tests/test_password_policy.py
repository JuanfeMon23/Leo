"""PasswordPolicy (reglas) y LeoClient.password_policy (endpoint publico)."""

import httpx
import pytest
from pydantic import ValidationError

from leo_sdk import (
    LeoClient,
    LeoSettings,
    LeoUnavailableError,
    PasswordPolicy,
    TooManyAttemptsError,
)
from leo_sdk.client import POLICY_CACHE_SECONDS

GOOD = "Clave-Segura-2026!"


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("Ab-1xyz", "too_short"),
        ("Ab-1" + "x" * 130, "too_long"),
        ("CLAVE-SEGURA-2026!", "no_lowercase"),
        ("clave-segura-2026!", "no_uppercase"),
        ("Clave-Segura-Sin-Digito!", "no_digit"),
        ("ClaveSegura2026Sinsimbolo", "no_symbol"),
    ],
)
def test_check_reporta_cada_requisito(password, code):
    assert PasswordPolicy().check(password) == [code]


def test_check_valida_y_acumula():
    policy = PasswordPolicy()
    assert policy.check(GOOD) == []
    assert policy.is_valid(GOOD)
    assert policy.check("abc") == ["too_short", "no_uppercase", "no_digit", "no_symbol"]
    assert not policy.is_valid("abc")


def test_check_respeta_minimo_y_clases_desactivadas():
    relaxed = PasswordPolicy(
        min_length=20,
        require_uppercase=False,
        require_digit=False,
        require_symbol=False,
    )
    assert relaxed.check("clavesegurasegura") == ["too_short"]
    assert relaxed.check("clavesegurasegurasegura") == []


def test_modelo_congelado():
    with pytest.raises(ValidationError):
        PasswordPolicy().min_length = 3  # type: ignore[misc]


BODY = {
    "min_length": 14,
    "max_length": 128,
    "require_lowercase": True,
    "require_uppercase": True,
    "require_digit": False,
    "require_symbol": True,
}


def make_client(handler):
    settings = LeoSettings(
        leo_url="https://leo.test",
        leo_api_url="https://leo.test/api/v1",
        app_client_id="app",
        app_client_secret="fake-secret-for-tests-only",
        public_url="https://app.test",
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LeoClient(settings, http=http)


async def test_password_policy_sin_auth_y_con_cache(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=BODY)

    client = make_client(handler)
    policy = await client.password_policy()
    assert policy == PasswordPolicy(**BODY)
    assert calls[0].url.path == "/api/v1/auth/password-policy"
    assert "authorization" not in calls[0].headers

    await client.password_policy()
    assert len(calls) == 1  # cache

    import leo_sdk.client as module

    real = module.time.monotonic()
    monkeypatch.setattr(
        module.time, "monotonic", lambda: real + POLICY_CACHE_SECONDS + 1
    )
    await client.password_policy()
    assert len(calls) == 2


async def test_password_policy_leo_caido():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(LeoUnavailableError):
        await make_client(handler).password_policy()


async def test_password_policy_error_http():
    client = make_client(
        lambda r: httpx.Response(429, json={}, headers={"retry-after": "5"})
    )
    with pytest.raises(TooManyAttemptsError):
        await client.password_policy()
