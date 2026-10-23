"""`LeoClient.update_user_profile` / `change_user_password`: autogestion en
nombre del usuario con token de servicio (Bearer, audiencia `leo`)."""

import json
from typing import Any

import httpx
import pytest

from leo_sdk import (
    InvalidTokenError,
    LeoClient,
    LeoError,
    LeoSettings,
    TooManyAttemptsError,
    UserProfile,
)

PROFILE = "/api/v1/users/service/delegated/profile"
PASSWORD = "/api/v1/users/service/delegated/password"


class FakeLeo:
    def __init__(self) -> None:
        self.issued = 0
        self.valid: set[str] = set()
        self.calls: list[tuple[str, str, dict[str, Any], str, str]] = []
        self.override: dict[str, httpx.Response] = {}
        self.expire_next_service_token = False

    async def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        auth = request.headers.get("authorization", "")
        if path == "/api/v1/auth/token":
            assert auth.startswith("Basic ")
            assert body == {"grant_type": "client_credentials", "audience": "leo"}
            self.issued += 1
            token = f"svc-{self.issued}"
            if not self.expire_next_service_token or self.issued > 1:
                self.valid.add(token)
            return httpx.Response(
                200,
                json={
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": 600,
                    "audience": "leo",
                },
            )
        self.calls.append((request.method, path, body, auth, ""))
        if auth.removeprefix("Bearer ") not in self.valid:
            return httpx.Response(
                401, json={"code": "invalid_token", "message": "m", "details": None}
            )
        if path in self.override:
            return self.override[path]
        if path == PROFILE:
            return httpx.Response(
                200,
                json={
                    "first_name": body.get("first_name", "Ana"),
                    "last_name": body.get("last_name", "Gómez"),
                    "email": body.get("email", "ana@example.com"),
                    "username": "ana",
                },
            )
        if path == PASSWORD:
            return httpx.Response(204)
        return httpx.Response(404, json={"code": "not_found"})


@pytest.fixture
async def parts():
    leo = FakeLeo()
    http = httpx.AsyncClient(transport=httpx.MockTransport(leo.handle))
    client = LeoClient(
        LeoSettings(
            leo_url="https://leo.test",
            leo_api_url="https://api.leo.test/api/v1",
            app_client_id="acu",
            app_client_secret="fake-secret-for-tests-only",
            public_url="https://app.test",
        ),
        http=http,
    )
    yield client, leo
    await http.aclose()


async def test_update_profile_sends_only_given_fields_with_bearer(parts) -> None:
    client, leo = parts
    out = await client.update_user_profile("user-tok", first_name="Laura")
    assert out == UserProfile(
        first_name="Laura", last_name="Gómez", email="ana@example.com", username="ana"
    )
    [(method, path, body, auth, _)] = leo.calls
    assert (method, path) == ("PATCH", PROFILE)
    assert body == {"user_access_token": "user-tok", "first_name": "Laura"}
    assert auth == "Bearer svc-1"


async def test_update_profile_email_with_current_password(parts) -> None:
    client, leo = parts
    await client.update_user_profile(
        "user-tok", email="n@example.com", current_password="Clave-1"
    )
    assert leo.calls[0][2] == {
        "user_access_token": "user-tok",
        "email": "n@example.com",
        "current_password": "Clave-1",
    }


async def test_change_password(parts) -> None:
    client, leo = parts
    assert await client.change_user_password("user-tok", "vieja", "nueva") is None
    method, path, body, _auth, _ = leo.calls[0]
    assert (method, path) == ("POST", PASSWORD)
    assert body == {
        "user_access_token": "user-tok",
        "current_password": "vieja",
        "new_password": "nueva",
    }


async def test_service_token_is_reused_across_calls(parts) -> None:
    client, leo = parts
    await client.update_user_profile("t", first_name="A")
    await client.change_user_password("t", "a", "b")
    assert leo.issued == 1


async def test_service_401_renews_token_and_retries_once(parts) -> None:
    client, leo = parts
    leo.expire_next_service_token = True  # el primer token ya nace rechazado
    out = await client.update_user_profile("t", first_name="A")
    assert out.first_name == "A"
    assert leo.issued == 2
    assert [c[3] for c in leo.calls] == ["Bearer svc-1", "Bearer svc-2"]


async def test_user_token_401_is_not_retried(parts) -> None:
    client, leo = parts
    leo.override[PROFILE] = httpx.Response(
        401,
        json={
            "code": "invalid_token",
            "message": "Token de usuario inválido o vencido.",
            "details": {"field": "user_access_token"},
        },
    )
    with pytest.raises(InvalidTokenError) as exc:
        await client.update_user_profile("t", first_name="A")
    assert exc.value.is_user_token
    assert exc.value.status_code == 401
    assert leo.issued == 1 and len(leo.calls) == 1


async def test_persistent_service_401_gives_up_after_one_retry(parts) -> None:
    client, leo = parts
    leo.expire_next_service_token = True
    leo.valid.clear()

    async def always_invalid(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/token"):
            leo.issued += 1
            return httpx.Response(
                200,
                json={"access_token": f"x{leo.issued}", "token_type": "Bearer",
                      "expires_in": 600, "audience": "leo"},
            )
        return httpx.Response(401, json={"code": "invalid_token", "message": "m"})

    client._http = httpx.AsyncClient(transport=httpx.MockTransport(always_invalid))
    with pytest.raises(InvalidTokenError) as exc:
        await client.change_user_password("t", "a", "b")
    assert not exc.value.is_user_token
    assert leo.issued == 2


@pytest.mark.parametrize(
    ("status", "code", "kind"),
    [
        (422, "current_password_required", LeoError),
        (403, "invalid_current_password", LeoError),
        (403, "forbidden", LeoError),
        (409, "duplicate", LeoError),
        (422, "weak_password", LeoError),
    ],
)
async def test_leo_errors_are_mapped(parts, status, code, kind) -> None:
    client, leo = parts
    leo.override[PROFILE] = httpx.Response(
        status, json={"code": code, "message": f"msg {code}", "details": None}
    )
    with pytest.raises(kind) as exc:
        await client.update_user_profile("t", email="x@example.com")
    assert (exc.value.code, exc.value.status_code) == (code, status)
    assert exc.value.message == f"msg {code}"


async def test_429_carries_retry_after(parts) -> None:
    client, leo = parts
    leo.override[PASSWORD] = httpx.Response(
        429,
        json={"code": "too_many_attempts", "message": "m", "details": None},
        headers={"Retry-After": "42"},
    )
    with pytest.raises(TooManyAttemptsError) as exc:
        await client.change_user_password("t", "a", "b")
    assert exc.value.retry_after == 42


async def test_invalid_credentials_401_is_not_retried(parts) -> None:
    client, leo = parts
    leo.override[PASSWORD] = httpx.Response(
        401, json={"code": "invalid_credentials", "message": "La contraseña actual no es correcta."}
    )
    with pytest.raises(LeoError) as exc:
        await client.change_user_password("t", "mala", "nueva")
    assert exc.value.code == "invalid_credentials"
    assert leo.issued == 1 and len(leo.calls) == 1
