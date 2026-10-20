"""Credenciales de servicio con un Leo simulado: proveedor de tokens (lado
consumidor) y `LeoAuth` aceptando `Authorization: Bearer` (lado audiencia)."""

import asyncio
import base64
import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from leo_sdk import (
    InvalidClientError,
    InvalidTargetError,
    LeoAuth,
    LeoClient,
    LeoSettings,
    LeoUnavailableError,
    LeoUser,
    ServiceAccessDenied,
    ServiceTokenProvider,
    TooManyAttemptsError,
    leo_router,
)
from tests.helpers import DpopKey

SECRET = "fake-secret-for-tests-only"
PUBLIC = "https://app.test"


def basic(client_id: str, secret: str = SECRET) -> str:
    return "Basic " + base64.b64encode(f"{client_id}:{secret}".encode()).decode()


class FakeLeo:
    """Emite tokens de servicio y los introspecciona (solo la audiencia)."""

    def __init__(self) -> None:
        self.exchanges: list[dict[str, Any]] = []
        self.introspections = 0
        self.tokens: dict[str, dict[str, Any]] = {}  # token -> datos
        self.permissions = ["app.things.view"]
        self.expires_in = 600
        self.down = False
        self.token_error: httpx.Response | None = None
        self.delay = 0.0
        self.events: list[dict[str, Any]] = []
        self.last_basic = ""

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down")
        path = request.url.path.removeprefix("/api/v1")
        auth = request.headers.get("authorization", "")
        self.last_basic = auth
        body = json.loads(request.content) if request.content else {}
        if path == "/auth/token":
            self.exchanges.append(body)
            if self.delay:
                await asyncio.sleep(self.delay)
            if auth != basic("caller"):
                return httpx.Response(401, json={"code": "invalid_client"})
            if self.token_error is not None:
                return self.token_error
            token = f"svc-{uuid4().hex}"
            self.tokens[token] = {"audience": body["audience"], "client": "caller"}
            return httpx.Response(
                200,
                json={
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": self.expires_in,
                    "audience": body["audience"],
                },
            )
        if path == "/auth/introspect":
            self.introspections += 1
            assert "jkt" not in body
            entry = self.tokens.get(body["token"])
            if auth != basic("app") or entry is None or entry["audience"] != "app":
                return httpx.Response(200, json={"active": False})
            return httpx.Response(
                200,
                json={
                    "active": True,
                    "principal_type": "service",
                    "client": {"client_id": entry["client"], "name": "Caller App"},
                    "permissions": self.permissions,
                    "exp": 4_000_000_000,
                },
            )
        if path == "/audit/events":
            self.events.append(body)
            return httpx.Response(201, json={"id": str(uuid4())})
        return httpx.Response(404, json={"code": "not_found"})


def err(status: int, code: str, headers: dict[str, str] | None = None):
    return httpx.Response(
        status,
        json={"code": code, "message": f"msg {code}", "details": None},
        headers=headers,
    )


def settings(client_id: str) -> LeoSettings:
    return LeoSettings(
        leo_url="https://leo.test",
        leo_api_url="https://api.leo.test/api/v1",
        app_client_id=client_id,
        app_client_secret=SECRET,
        public_url=PUBLIC,
    )


@pytest.fixture
def leo() -> FakeLeo:
    return FakeLeo()


# --- lado consumidor: ServiceTokenProvider ---


@pytest_asyncio.fixture
async def provider_parts(leo: FakeLeo):
    http = httpx.AsyncClient(transport=httpx.MockTransport(leo.handle))
    now = [1000.0]
    client = LeoClient(settings("caller"), http=http)
    provider = ServiceTokenProvider(client, clock=lambda: now[0])
    yield provider, now
    await http.aclose()


async def test_token_is_cached_until_margin_before_expiry(
    provider_parts, leo: FakeLeo
) -> None:
    provider, now = provider_parts
    first = await provider.token("target")
    assert await provider.token("target") == first
    assert len(leo.exchanges) == 1
    assert leo.exchanges[0] == {
        "grant_type": "client_credentials",
        "audience": "target",
    }
    assert leo.last_basic == basic("caller")
    now[0] += 569  # 600 - 30 de margen = 570
    assert await provider.token("target") == first
    now[0] += 2
    assert await provider.token("target") != first
    assert len(leo.exchanges) == 2


async def test_cache_is_per_audience(provider_parts, leo: FakeLeo) -> None:
    provider, _ = provider_parts
    a = await provider.token("one")
    b = await provider.token("two")
    assert a != b and len(leo.exchanges) == 2


async def test_short_lived_token_still_cached_with_half_life(
    provider_parts, leo: FakeLeo
) -> None:
    provider, now = provider_parts
    leo.expires_in = 20  # menor que el margen de 30 s
    first = await provider.token("target")
    now[0] += 5
    assert await provider.token("target") == first
    now[0] += 6
    assert await provider.token("target") != first


async def test_concurrent_callers_cause_a_single_exchange(
    provider_parts, leo: FakeLeo
) -> None:
    provider, _ = provider_parts
    leo.delay = 0.05
    tokens = await asyncio.gather(*(provider.token("target") for _ in range(20)))
    assert len(set(tokens)) == 1 and len(leo.exchanges) == 1


async def test_headers_returns_bearer(provider_parts) -> None:
    provider, _ = provider_parts
    headers = await provider.headers("target")
    token = await provider.token("target")
    assert headers == {"Authorization": f"Bearer {token}"}


async def test_invalidate_forces_new_exchange(provider_parts, leo: FakeLeo) -> None:
    provider, _ = provider_parts
    first = await provider.token("target")
    provider.invalidate("target")
    assert await provider.token("target") != first


@pytest.mark.parametrize(
    ("response", "exc"),
    [
        (err(403, "access_denied"), ServiceAccessDenied),
        (err(400, "invalid_target"), InvalidTargetError),
        (err(429, "too_many_attempts", {"Retry-After": "7"}), TooManyAttemptsError),
        (err(503, "oops"), LeoUnavailableError),
    ],
)
async def test_readable_typed_errors_and_not_cached(
    provider_parts, leo: FakeLeo, response: httpx.Response, exc: type
) -> None:
    provider, _ = provider_parts
    leo.token_error = response
    with pytest.raises(exc) as info:
        await provider.token("target")
    assert info.value.message
    if exc is TooManyAttemptsError:
        assert info.value.retry_after == 7
    leo.token_error = None  # los errores no se cachean
    assert await provider.token("target")


async def test_leo_down_is_leo_unavailable(provider_parts, leo: FakeLeo) -> None:
    provider, _ = provider_parts
    leo.down = True
    with pytest.raises(LeoUnavailableError):
        await provider.token("target")


async def test_wrong_secret_is_invalid_client(leo: FakeLeo) -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(leo.handle))
    bad = LeoSettings(
        leo_url="https://leo.test",
        leo_api_url="https://api.leo.test/api/v1",
        app_client_id="other",
        app_client_secret="wrong",
        public_url=PUBLIC,
    )
    with pytest.raises(InvalidClientError):
        await ServiceTokenProvider(LeoClient(bad, http=http)).token("target")
    await http.aclose()


async def test_never_logs_or_reprs_token_or_secret(
    provider_parts, leo: FakeLeo, caplog: pytest.LogCaptureFixture
) -> None:
    provider, _ = provider_parts
    caplog.set_level(logging.DEBUG)
    token = await provider.token("target")
    leo.token_error = err(403, "access_denied")
    provider.invalidate()
    with pytest.raises(ServiceAccessDenied) as info:
        await provider.token("target")
    leo.token_error = None
    issued = await provider._client.client_credentials("target")
    blob = caplog.text + repr(issued) + repr(info.value) + repr(provider.auth("t"))
    assert token not in blob and issued.access_token not in blob
    assert SECRET not in blob


# --- httpx.Auth con reintento ---


def target_app(valid: set[str], seen: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        seen.append(auth)
        ok = auth.removeprefix("Bearer ") in valid
        return httpx.Response(200 if ok else 401, json={"ok": ok})

    return httpx.MockTransport(handler)


async def test_auth_retries_once_with_a_new_token_on_401(
    provider_parts, leo: FakeLeo
) -> None:
    provider, _ = provider_parts
    old = await provider.token("target")  # el destino ya no lo acepta
    seen: list[str] = []
    valid: set[str] = set()
    transport = target_app(valid, seen)
    async with httpx.AsyncClient(
        transport=transport, auth=provider.auth("target")
    ) as http:
        # el destino acepta solo tokens emitidos despues
        original = leo.handle

        async def issuing(request: httpx.Request) -> httpx.Response:
            response = await original(request)
            if request.url.path.endswith("/auth/token"):
                valid.add(json.loads(response.content)["access_token"])
            return response

        provider._client._http._transport = httpx.MockTransport(issuing)
        response = await http.get("https://target.test/x")
    assert response.status_code == 200
    assert len(seen) == 2 and seen[0] == f"Bearer {old}" and seen[1] != seen[0]
    assert len(leo.exchanges) == 2


async def test_auth_does_not_loop_on_persistent_401(
    provider_parts, leo: FakeLeo
) -> None:
    provider, _ = provider_parts
    seen: list[str] = []
    async with httpx.AsyncClient(
        transport=target_app(set(), seen), auth=provider.auth("target")
    ) as http:
        response = await http.get("https://target.test/x")
    assert response.status_code == 401
    assert len(seen) == 2 and len(leo.exchanges) == 2


async def test_auth_reuses_cached_token_across_requests(
    provider_parts, leo: FakeLeo
) -> None:
    provider, _ = provider_parts
    seen: list[str] = []
    token = await provider.token("target")
    async with httpx.AsyncClient(
        transport=target_app({token}, seen), auth=provider.auth("target")
    ) as http:
        for _ in range(3):
            assert (await http.get("https://target.test/x")).status_code == 200
    assert len(leo.exchanges) == 1 and len(seen) == 3


# --- lado audiencia: LeoAuth acepta Bearer de servicio ---


@pytest_asyncio.fixture
async def audience(leo: FakeLeo) -> AsyncGenerator[tuple[LeoAuth, FastAPI]]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(leo.handle))
    s = settings("app")
    auth = LeoAuth(s, client=LeoClient(s, http=http))
    app = FastAPI()
    auth.install(app)
    app.include_router(leo_router(auth))
    view = Annotated[LeoUser, auth.require_action("app.things.view")]
    edit = Annotated[LeoUser, auth.require_action("app.things.edit")]
    anyone = Annotated[LeoUser, __import__("fastapi").Depends(auth.current_user)]
    person = Annotated[LeoUser, __import__("fastapi").Depends(auth.current_person)]

    @app.get("/things")
    async def things(user: view) -> dict:
        return {
            "type": user.principal_type,
            "client_id": user.client_id,
            "permissions": sorted(user.permissions),
            "session_id": user.session_id,
        }

    @app.post("/things")
    async def change(user: edit) -> dict:
        return {"ok": True}

    @app.get("/who")
    async def who(user: anyone) -> dict:
        return {"type": user.principal_type}

    @app.get("/people-only")
    async def people_only(user: person) -> dict:
        return {"type": user.principal_type}

    yield auth, app
    await http.aclose()


def call(app: FastAPI, method: str, path: str, **kw: Any):
    cookies = kw.pop("cookies", None)
    if cookies:
        kw["headers"] = {
            **kw.get("headers", {}),
            "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        }

    async def run() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=PUBLIC
        ) as http:
            return await http.request(method, path, **kw)

    return run()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def issue(leo: FakeLeo, audience: str = "app") -> str:
    token = f"svc-{uuid4().hex}"
    leo.tokens[token] = {"audience": audience, "client": "caller"}
    return token


async def test_valid_service_bearer_is_200_with_permissions_and_no_dpop(
    audience, leo: FakeLeo
) -> None:
    _, app = audience
    response = await call(app, "GET", "/things", headers=bearer(issue(leo)))
    assert response.status_code == 200
    assert response.json() == {
        "type": "service",
        "client_id": "caller",
        "permissions": ["app.things.view"],
        "session_id": None,
    }


async def test_service_without_permission_is_403_with_denied_event(
    audience, leo: FakeLeo
) -> None:
    _, app = audience
    response = await call(app, "POST", "/things", headers=bearer(issue(leo)))
    assert response.status_code == 403 and response.json()["code"] == "forbidden"
    event = leo.events[-1]
    assert event["action_tag"] == "app.things.edit" and event["result"] == "denied"
    assert "actor" not in event and "actor_user_id" not in event
    assert "caller" in event["reason"]  # la app llamadora queda en el motivo
    assert "svc-" not in json.dumps(event)


@pytest.mark.parametrize("kind", ["unknown", "other_audience", "empty", "malformed"])
async def test_invalid_service_tokens_are_401(
    audience, leo: FakeLeo, kind: str
) -> None:
    _, app = audience
    headers = {
        "unknown": bearer("svc-nope"),
        "other_audience": bearer(issue(leo, audience="someone-else")),
        "empty": {"Authorization": "Bearer "},
        "malformed": {"Authorization": "Bearer a b c"},
    }[kind]
    response = await call(app, "GET", "/things", headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["www-authenticate"] == "Bearer"


async def test_invalid_bearer_does_not_fall_back_to_cookie(
    audience, leo: FakeLeo
) -> None:
    _, app = audience
    response = await call(
        app,
        "GET",
        "/things",
        headers=bearer("svc-nope"),
        cookies={"__Host-leo_access": "whatever"},
    )
    assert (
        response.status_code == 401 and response.json()["code"] == "not_authenticated"
    )


async def test_non_bearer_authorization_is_ignored_and_cookie_path_used(
    audience,
) -> None:
    _, app = audience
    response = await call(app, "GET", "/things", headers={"Authorization": "Basic abc"})
    assert (
        response.status_code == 401 and response.json()["code"] == "not_authenticated"
    )
    assert "DPoP" in response.headers["www-authenticate"]


async def test_service_bearer_cannot_use_session_routes(audience, leo: FakeLeo) -> None:
    _, app = audience
    headers = bearer(issue(leo))
    for method, path in [
        ("GET", "/auth/me"),
        ("POST", "/auth/activity"),
        ("POST", "/auth/logout"),
        ("GET", "/people-only"),
    ]:
        response = await call(app, method, path, headers=headers)
        assert response.status_code == 403, path
        assert response.json()["code"] == "user_required"
    assert leo.introspections == 0  # ni siquiera se canjea/valida


async def test_current_user_distinguishes_principal_type(
    audience, leo: FakeLeo
) -> None:
    _, app = audience
    response = await call(app, "GET", "/who", headers=bearer(issue(leo)))
    assert response.json() == {"type": "service"}


async def test_user_cookie_path_still_requires_dpop(audience) -> None:
    _, app = audience
    response = await call(app, "GET", "/things", cookies={"__Host-leo_access": "tok"})
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_dpop_proof"


async def test_user_cookie_with_dpop_still_works(audience, leo: FakeLeo) -> None:
    """Un usuario (cookie + DPoP) sigue entrando; el servicio no se mezcla."""
    auth, app = audience
    key = DpopKey()
    user_id, session_id = uuid4(), uuid4()
    original = leo.handle

    async def with_users(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if request.url.path.endswith("/auth/introspect") and "jkt" in body:
            return httpx.Response(
                200,
                json={
                    "active": True,
                    "user": {
                        "id": str(user_id),
                        "username": "ana",
                        "name": "Ana",
                        "email": "ana@example.com",
                    },
                    "permissions": ["app.things.view"],
                    "session_id": str(session_id),
                    "exp": 4_000_000_000,
                },
            )
        return await original(request)

    auth.client._http._transport = httpx.MockTransport(with_users)
    response = await call(
        app,
        "GET",
        "/things",
        cookies={"__Host-leo_access": "tok"},
        headers={"DPoP": key.proof("GET", PUBLIC + "/things")},
    )
    assert response.status_code == 200
    assert response.json()["type"] == "user" and response.json()["client_id"] is None


async def test_service_introspection_is_cached_30s(audience, leo: FakeLeo) -> None:
    auth, app = audience
    now = [1000.0]
    auth.sessions._cache._clock = lambda: now[0]
    token = issue(leo)
    for _ in range(3):
        assert (
            await call(app, "GET", "/things", headers=bearer(token))
        ).status_code == 200
    assert leo.introspections == 1
    now[0] += 31
    assert (await call(app, "GET", "/things", headers=bearer(token))).status_code == 200
    assert leo.introspections == 2


async def test_revoked_token_stops_after_cache_expires(audience, leo: FakeLeo) -> None:
    auth, app = audience
    now = [1000.0]
    auth.sessions._cache._clock = lambda: now[0]
    token = issue(leo)
    assert (await call(app, "GET", "/things", headers=bearer(token))).status_code == 200
    del leo.tokens[token]  # revocado en Leo (quitaron la concesion)
    # dentro de la ventana de cache aun sirve (maximo 30 s)
    assert (await call(app, "GET", "/things", headers=bearer(token))).status_code == 200
    now[0] += 31
    response = await call(app, "GET", "/things", headers=bearer(token))
    assert response.status_code == 401


async def test_inactive_tokens_are_never_cached(audience, leo: FakeLeo) -> None:
    auth, app = audience
    for _ in range(3):
        response = await call(app, "GET", "/things", headers=bearer("svc-nope"))
        assert response.status_code == 401
    assert leo.introspections == 3
    assert len(auth.sessions._cache) == 0


async def test_cached_service_token_requires_its_own_key(
    audience, leo: FakeLeo
) -> None:
    """Un token distinto no hereda el acierto de cache de otro."""
    _, app = audience
    good = issue(leo)
    assert (await call(app, "GET", "/things", headers=bearer(good))).status_code == 200
    other = await call(app, "GET", "/things", headers=bearer(good + "x"))
    assert other.status_code == 401


async def test_leo_down_is_503_for_service_bearer(audience, leo: FakeLeo) -> None:
    _, app = audience
    leo.down = True
    response = await call(app, "GET", "/things", headers=bearer(issue(leo)))
    assert response.status_code == 503
    assert response.json()["code"] == "leo_unavailable"
