"""BFF con un Leo simulado (httpx.MockTransport): login, sesion, cache de
introspeccion, refresh, require_action, auditoria y catalogo."""

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from typing import Annotated, Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr

from leo_sdk import (
    AuditClient,
    Catalog,
    CatalogMismatchError,
    LeoAuth,
    LeoClient,
    LeoSettings,
    LeoUser,
    leo_router,
)
from leo_sdk.errors import InvalidClientError, InvalidGrantError, LeoUnavailableError
from leo_sdk.oauth import pkce_challenge
from tests.helpers import DpopKey

PUBLIC = "https://app.test"
SECRET = "fake-secret-for-tests-only"
USER_ID = uuid4()
SESSION_ID = uuid4()


class FakeLeo:
    """Servidor de Leo minimo: guarda codes/tokens y cuenta llamadas."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.active_access: dict[str, str] = {}  # access -> jkt
        self.refresh_tokens: dict[str, str] = {}  # refresh -> jkt
        self.used_refresh: set[str] = set()
        self.codes: dict[str, dict[str, str]] = {}
        self.permissions = ["app.things.view"]
        self.events: list[dict[str, Any]] = []
        self.down = False
        self.reject_actor = False
        self.catalog_payload: dict[str, Any] | None = None
        self.basic_seen: list[str] = []
        self.refresh_delay = 0.0
        self.extra_introspect: dict[str, Any] = {}
        self.extra_user: dict[str, Any] = {}

    def count(self, path: str) -> int:
        return sum(1 for _, p in self.calls if p == path)

    def issue(self, jkt: str) -> dict[str, Any]:
        access, refresh = f"acc-{uuid4().hex}", f"ref-{uuid4().hex}"
        self.active_access[access] = jkt
        self.refresh_tokens[refresh] = jkt
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "DPoP",
            "expires_in": 900,
            "refresh_expires_in": 43200,
            "session_id": str(SESSION_ID),
        }

    def err(self, status: int, code: str) -> httpx.Response:
        return httpx.Response(
            status, json={"code": code, "message": f"msg {code}", "details": None}
        )

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down")
        path = request.url.path.removeprefix("/api/v1")
        self.calls.append((request.method, path))
        auth = request.headers.get("authorization", "")
        self.basic_seen.append(auth)
        expected = base64.b64encode(f"app:{SECRET}".encode()).decode()
        if auth != f"Basic {expected}":
            return self.err(401, "invalid_client")
        body = json.loads(request.content) if request.content else {}
        if path == "/auth/token" and body["grant_type"] == "authorization_code":
            entry = self.codes.pop(body["code"], None)
            if (
                entry is None
                or entry["jkt"] != body["jkt"]
                or pkce_challenge(body["code_verifier"]) != entry["challenge"]
            ):
                return self.err(400, "invalid_grant")
            return httpx.Response(200, json=self.issue(body["jkt"]))
        if path == "/auth/token":
            if self.refresh_delay:
                await asyncio.sleep(self.refresh_delay)
            token = body["refresh_token"]
            if (
                token in self.used_refresh
                or self.refresh_tokens.get(token) != body["jkt"]
            ):
                return self.err(400, "invalid_grant")
            self.used_refresh.add(token)
            return httpx.Response(200, json=self.issue(body["jkt"]))
        if path == "/auth/introspect":
            if self.active_access.get(body["token"]) != body["jkt"]:
                return httpx.Response(200, json={"active": False})
            return httpx.Response(
                200,
                json={
                    "active": True,
                    "user": {
                        "id": str(USER_ID),
                        "username": "ana",
                        "name": "Ana Gómez",
                        "email": "ana@example.com",
                        **self.extra_user,
                    },
                    "permissions": self.permissions,
                    "session_id": str(SESSION_ID),
                    "client_id": "app",
                    "exp": 4_000_000_000,
                    "idle_timeout_seconds": 1800,
                    **self.extra_introspect,
                },
            )
        if path == "/auth/revoke":
            if self.active_access.get(body["token"]) == body["jkt"]:
                self.active_access.pop(body["token"])
            return httpx.Response(204)
        if path == "/audit/events":
            if self.reject_actor and "actor" in body:
                return self.err(422, "invalid_actor")
            self.events.append(body)
            return httpx.Response(201, json={"id": str(uuid4())})
        if path == "/applications/app/catalog":
            self.catalog_payload = body
            return httpx.Response(200, json={"created_actions": ["app.things.view"]})
        return self.err(404, "not_found")


class Browser:
    def __init__(self, app: FastAPI) -> None:
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=PUBLIC
        )
        self.key = DpopKey()

    async def call(
        self,
        method: str,
        path: str,
        *,
        key: DpopKey | None = None,
        proof: bool = True,
        **kw: Any,
    ) -> httpx.Response:
        headers = dict(kw.pop("headers", {}))
        if proof:
            headers["DPoP"] = (key or self.key).proof(
                method, PUBLIC + path.split("?")[0]
            )
        return await self.http.request(method, path, headers=headers, **kw)

    async def login(self, leo: FakeLeo) -> httpx.Response:
        """Recorre login -> authorize (simulado) -> callback."""
        started = await self.call("GET", "/auth/login")
        assert started.status_code == 200, started.text
        query = parse_qs(urlsplit(started.json()["authorize_url"]).query)
        code = f"code-{uuid4().hex}"
        leo.codes[code] = {
            "jkt": query["dpop_jkt"][0],
            "challenge": query["code_challenge"][0],
        }
        return await self.call(
            "GET", f"/auth/callback?code={code}&state={query['state'][0]}"
        )


def make_catalog() -> Catalog:
    catalog = Catalog("app")
    catalog.module("things", "Cosas")
    catalog.action("things", "view", "Ver cosas")
    catalog.action("things", "edit", "Editar cosas", "Cambia una cosa")
    return catalog


@pytest.fixture
def leo() -> FakeLeo:
    return FakeLeo()


@pytest.fixture
def settings() -> LeoSettings:
    return LeoSettings(
        leo_url="https://leo.test",
        leo_api_url="https://api.leo.test/api/v1",
        app_client_id="app",
        app_client_secret=SECRET,
        public_url=PUBLIC,
    )


@pytest_asyncio.fixture
async def auth(leo: FakeLeo, settings: LeoSettings) -> AsyncGenerator[LeoAuth]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(leo.handle))
    instance = LeoAuth(
        settings, catalog=make_catalog(), client=LeoClient(settings, http=http)
    )
    yield instance
    await http.aclose()


@pytest.fixture
def app(auth: LeoAuth) -> FastAPI:
    application = FastAPI()
    auth.install(application)
    application.include_router(leo_router(auth))
    CurrentUser = Annotated[LeoUser, auth.require_action("app.things.view")]
    Editor = Annotated[LeoUser, auth.require_action("app.things.edit")]

    @application.get("/things")
    async def things(user: CurrentUser) -> dict[str, str]:
        return {"user": user.username}

    @application.post("/things")
    async def edit(user: Editor) -> dict[str, str]:
        return {"ok": user.username}

    return application


@pytest_asyncio.fixture
async def browser(app: FastAPI) -> AsyncGenerator[Browser]:
    b = Browser(app)
    yield b
    await b.http.aclose()


# --- settings / cliente ---


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "LEO_URL": "https://leo.x",
        "LEO_API_URL": "https://api.x/api/v1",
        "APP_CLIENT_ID": "app",
        "APP_CLIENT_SECRET": "s3",
        "PUBLIC_URL": "https://a.x",
    }.items():
        monkeypatch.setenv(key, value)
    s = LeoSettings()
    assert s.app_client_secret.get_secret_value() == "s3"
    assert "s3" not in repr(s)
    assert s.callback_url == "https://a.x/auth/callback"
    assert s.cookie_name("leo_access") == "__Host-leo_access"


def test_cookie_names_without_secure(settings: LeoSettings) -> None:
    s = settings.model_copy(update={"cookie_secure": False})
    assert s.cookie_name("leo_access") == "leo_access"


async def test_client_sends_basic_auth_and_maps_errors(
    leo: FakeLeo, settings: LeoSettings
) -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(leo.handle))
    client = LeoClient(settings, http=http)
    with pytest.raises(InvalidGrantError) as grant:
        await client.refresh("nope", "J" * 43)
    assert grant.value.code == "invalid_grant" and grant.value.status_code == 400
    bad = LeoClient(
        settings.model_copy(update={"app_client_secret": SecretStr("wrong")}), http=http
    )
    with pytest.raises(InvalidClientError) as invalid:
        await bad.introspect("t", "J" * 43)
    assert invalid.value.status_code == 401
    leo.down = True
    with pytest.raises(LeoUnavailableError):
        await client.introspect("t", "J" * 43)


# --- login ---


async def test_full_login_sets_httponly_cookies_and_no_tokens_in_body(
    browser: Browser, leo: FakeLeo
) -> None:
    response = await browser.login(leo)
    assert response.status_code == 200, response.text
    body = response.text
    assert "acc-" not in body and "ref-" not in body
    assert response.json()["user"]["permissions"] == ["app.things.view"]
    cookies = response.headers.get_list("set-cookie")
    joined = "\n".join(cookies)
    assert "__Host-leo_access=" in joined and "__Host-leo_refresh=" in joined
    for cookie in cookies:
        low = cookie.lower()
        if "leo_oauth" in low:
            assert "max-age=0" in low
            continue
        assert "httponly" in low and "secure" in low and "samesite=strict" in low
        assert "path=/" in low and "domain" not in low


async def test_login_requires_dpop_proof(browser: Browser) -> None:
    response = await browser.call("GET", "/auth/login", proof=False)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_dpop_proof"


async def test_callback_with_wrong_state_is_rejected(
    browser: Browser, leo: FakeLeo
) -> None:
    started = await browser.call("GET", "/auth/login")
    query = parse_qs(urlsplit(started.json()["authorize_url"]).query)
    leo.codes["c1"] = {
        "jkt": query["dpop_jkt"][0],
        "challenge": query["code_challenge"][0],
    }
    response = await browser.call("GET", "/auth/callback?code=c1&state=forged")
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_state"
    assert leo.count("/auth/token") == 0


async def test_callback_without_flow_cookie(browser: Browser) -> None:
    response = await browser.call("GET", "/auth/callback?code=c&state=s")
    assert response.status_code == 400 and response.json()["code"] == "invalid_state"


async def test_callback_from_another_browser_key_is_rejected(
    app: FastAPI, browser: Browser, leo: FakeLeo
) -> None:
    started = await browser.call("GET", "/auth/login")
    query = parse_qs(urlsplit(started.json()["authorize_url"]).query)
    leo.codes["c1"] = {
        "jkt": query["dpop_jkt"][0],
        "challenge": query["code_challenge"][0],
    }
    attacker_key = DpopKey()
    response = await browser.call(
        "GET", f"/auth/callback?code=c1&state={query['state'][0]}", key=attacker_key
    )
    assert response.status_code == 400 and response.json()["code"] == "invalid_state"
    assert "c1" in leo.codes  # el code no se gasto


async def test_tampered_flow_cookie_is_rejected(browser: Browser, leo: FakeLeo) -> None:
    started = await browser.call("GET", "/auth/login")
    query = parse_qs(urlsplit(started.json()["authorize_url"]).query)
    name = "__Host-leo_oauth"
    value = browser.http.cookies[name]
    browser.http.cookies.set(name, value[:-3] + "AAA", domain="app.test")
    leo.codes["c1"] = {
        "jkt": query["dpop_jkt"][0],
        "challenge": query["code_challenge"][0],
    }
    response = await browser.call(
        "GET", f"/auth/callback?code=c1&state={query['state'][0]}"
    )
    assert response.status_code == 400


async def test_callback_with_leo_error_param(browser: Browser) -> None:
    await browser.call("GET", "/auth/login")
    response = await browser.call("GET", "/auth/callback?error=access_denied&state=x")
    assert response.status_code == 400


async def test_code_replay_is_invalid_grant(browser: Browser, leo: FakeLeo) -> None:
    started = await browser.call("GET", "/auth/login")
    query = parse_qs(urlsplit(started.json()["authorize_url"]).query)
    leo.codes["c1"] = {
        "jkt": query["dpop_jkt"][0],
        "challenge": query["code_challenge"][0],
    }
    url = f"/auth/callback?code=c1&state={query['state'][0]}"
    assert (await browser.call("GET", url)).status_code == 200
    # El flujo ya se consumio (cookie borrada): reintentar no llega a Leo.
    again = await browser.call("GET", url)
    assert again.status_code == 400


# --- sesion / cache ---


async def test_me_and_introspection_cache(
    auth: LeoAuth, browser: Browser, leo: FakeLeo
) -> None:
    await browser.login(leo)
    auth.sessions._cache.clear()
    leo.calls.clear()
    for _ in range(3):
        response = await browser.call("GET", "/auth/me")
        assert response.status_code == 200
    assert leo.count("/auth/introspect") == 1  # caché de 30 s


def _assert_me_shape(body: dict[str, Any]) -> None:
    assert set(body) == {"user", "session", "applications"}
    assert set(body["session"]) == {
        "expires_at",
        "last_activity_at",
        "idle_timeout_seconds",
    }


async def test_me_and_callback_without_new_fields_use_fallbacks(
    browser: Browser, leo: FakeLeo
) -> None:
    callback = await browser.login(leo)
    me = await browser.call("GET", "/auth/me")
    for body in (callback.json(), me.json()):
        _assert_me_shape(body)
        assert body["applications"] == []
        assert body["user"]["first_name"] == "Ana Gómez"
        assert body["user"]["last_name"] == ""
        assert body["user"]["name"] == "Ana Gómez"
        assert body["user"]["permissions"] == ["app.things.view"]
        assert body["session"]["idle_timeout_seconds"] == 1800
        assert body["session"]["expires_at"] == "2096-10-02T07:06:40Z"
        assert body["session"]["last_activity_at"].endswith("Z")
    assert "acc-" not in me.text


async def test_me_and_callback_use_new_fields_when_leo_sends_them(
    browser: Browser, leo: FakeLeo
) -> None:
    leo.extra_user = {"first_name": "Ana", "last_name": "Gómez"}
    leo.extra_introspect = {
        "applications": [
            {"slug": "app", "name": "App", "base_url": "https://app.test"}
        ],
        "last_activity_at": "2030-01-02T03:04:05Z",
    }
    callback = await browser.login(leo)
    me = await browser.call("GET", "/auth/me")
    for body in (callback.json(), me.json()):
        _assert_me_shape(body)
        assert body["applications"] == [
            {"slug": "app", "name": "App", "base_url": "https://app.test"}
        ]
        assert body["user"]["first_name"] == "Ana"
        assert body["user"]["last_name"] == "Gómez"
        assert body["session"]["last_activity_at"] == "2030-01-02T03:04:05Z"


async def test_unknown_application_fields_are_not_leaked(
    browser: Browser, leo: FakeLeo
) -> None:
    leo.extra_introspect = {
        "applications": [
            {"slug": "a", "name": "A", "base_url": "https://a.test", "secret": "x"}
        ]
    }
    await browser.login(leo)
    me = await browser.call("GET", "/auth/me")
    assert me.json()["applications"] == [
        {"slug": "a", "name": "A", "base_url": "https://a.test"}
    ]


async def test_cache_expires_after_ttl(
    app: FastAPI, auth: LeoAuth, browser: Browser, leo: FakeLeo
) -> None:
    now = [1000.0]
    auth.sessions._cache._clock = lambda: now[0]
    await browser.login(leo)
    auth.sessions._cache.clear()
    leo.calls.clear()
    await browser.call("GET", "/auth/me")
    now[0] += 31
    await browser.call("GET", "/auth/me")
    assert leo.count("/auth/introspect") == 2


async def test_cached_token_is_bound_to_jkt(browser: Browser, leo: FakeLeo) -> None:
    await browser.login(leo)
    await browser.call("GET", "/auth/me")  # llena la cache
    thief = await browser.call("GET", "/auth/me", key=DpopKey())
    assert thief.status_code == 401  # cookie robada con otra llave


async def test_stolen_cookie_without_proof(browser: Browser, leo: FakeLeo) -> None:
    await browser.login(leo)
    response = await browser.call("GET", "/auth/me", proof=False)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_dpop_proof"


async def test_proof_replay_is_rejected(browser: Browser, leo: FakeLeo) -> None:
    await browser.login(leo)
    proof = browser.key.proof("GET", PUBLIC + "/auth/me")
    first = await browser.http.get("/auth/me", headers={"DPoP": proof})
    second = await browser.http.get("/auth/me", headers={"DPoP": proof})
    assert first.status_code == 200 and second.status_code == 401


async def test_no_cookies_is_not_authenticated(browser: Browser) -> None:
    response = await browser.call("GET", "/auth/me")
    assert (
        response.status_code == 401 and response.json()["code"] == "not_authenticated"
    )


async def test_heartbeat_bypasses_cache(browser: Browser, leo: FakeLeo) -> None:
    await browser.login(leo)
    await browser.call("GET", "/auth/me")
    leo.calls.clear()
    response = await browser.call("POST", "/auth/activity")
    assert response.status_code == 204
    assert leo.count("/auth/introspect") == 1


async def test_transparent_refresh_when_access_expired(
    auth: LeoAuth, browser: Browser, leo: FakeLeo
) -> None:
    await browser.login(leo)
    auth.sessions._cache.clear()
    leo.active_access.clear()  # el access vencio en Leo
    browser.http.cookies.set("x", "y")
    old_refresh = browser.http.cookies["__Host-leo_refresh"]
    response = await browser.call("GET", "/auth/me")
    assert response.status_code == 200
    assert browser.http.cookies["__Host-leo_refresh"] != old_refresh
    assert leo.count("/auth/token") == 2  # canje + refresh


async def test_concurrent_requests_refresh_once(
    auth: LeoAuth, browser: Browser, leo: FakeLeo
) -> None:
    await browser.login(leo)
    auth.sessions._cache.clear()
    leo.active_access.clear()
    leo.refresh_delay = 0.05
    leo.calls.clear()
    responses = await asyncio.gather(
        *(browser.call("GET", "/auth/me") for _ in range(4))
    )
    assert [r.status_code for r in responses] == [200] * 4
    assert leo.count("/auth/token") == 1


async def test_refresh_reuse_kills_session_and_clears_cookies(
    auth: LeoAuth, browser: Browser, leo: FakeLeo
) -> None:
    await browser.login(leo)
    auth.sessions._cache.clear()
    refresh = browser.http.cookies["__Host-leo_refresh"]
    leo.used_refresh.add(refresh)
    leo.active_access.clear()
    response = await browser.call("GET", "/auth/me")
    assert response.status_code == 401 and response.json()["code"] == "session_expired"
    assert "max-age=0" in "\n".join(response.headers.get_list("set-cookie")).lower()


async def test_logout_revokes_clears_cookies_and_cache(
    browser: Browser, leo: FakeLeo
) -> None:
    await browser.login(leo)
    await browser.call("GET", "/auth/me")
    access = browser.http.cookies["__Host-leo_access"]
    response = await browser.call("POST", "/auth/logout")
    assert response.status_code == 204
    assert access not in leo.active_access
    assert "max-age=0" in "\n".join(response.headers.get_list("set-cookie")).lower()
    after = await browser.call("GET", "/auth/me")
    assert after.status_code == 401


async def test_logout_invalidates_cached_introspection(
    auth: LeoAuth, browser: Browser, leo: FakeLeo
) -> None:
    await browser.login(leo)
    await browser.call("GET", "/auth/me")
    access = browser.http.cookies["__Host-leo_access"]
    saved = access
    await browser.call("POST", "/auth/logout")
    browser.http.cookies.set("__Host-leo_access", saved, domain="app.test")
    response = await browser.call("GET", "/auth/me")
    assert response.status_code == 401  # no se sirve desde la cache


async def test_leo_down_is_503_and_keeps_cookies(
    browser: Browser, leo: FakeLeo
) -> None:
    await browser.login(leo)
    leo.down = True
    response = await browser.call("GET", "/auth/me", headers={})
    # La primera introspeccion estaba cacheada por el callback: fuerza miss.
    response = await browser.call("POST", "/auth/activity")
    assert response.status_code == 503
    assert response.json()["code"] == "leo_unavailable"
    assert "__Host-leo_access" in browser.http.cookies


# --- require_action / auditoria ---


async def test_require_action_allowed_and_denied_with_audit(
    browser: Browser, leo: FakeLeo
) -> None:
    await browser.login(leo)
    ok = await browser.call("GET", "/things")
    assert ok.status_code == 200 and ok.json() == {"user": "ana"}
    denied = await browser.call("POST", "/things")
    assert denied.status_code == 403
    assert denied.json()["code"] == "forbidden"
    event = leo.events[-1]
    assert event["action_tag"] == "app.things.edit" and event["result"] == "denied"
    assert event["actor"]["jkt"] == browser.key.jkt


def test_require_action_validates_tag(auth: LeoAuth) -> None:
    from leo_sdk import InvalidTagError

    for bad in ("leo.users.view", "app.things", "App.things.view", "Evento: x"):
        with pytest.raises(InvalidTagError):
            auth.require_action(bad)


def test_catalog_check_detects_undeclared_tags(auth: LeoAuth) -> None:
    auth.require_action("app.things.view")
    auth.check_catalog()  # declarado: no falla
    auth.require_action("app.things.delete")
    with pytest.raises(CatalogMismatchError) as exc:
        auth.check_catalog()
    assert exc.value.missing == ["app.things.delete"]


async def test_sync_catalog_publishes_payload(auth: LeoAuth, leo: FakeLeo) -> None:
    result = await auth.sync_catalog()
    assert result["created_actions"] == ["app.things.view"]
    assert leo.catalog_payload == {
        "modules": [
            {
                "slug": "things",
                "name": "Cosas",
                "actions": [
                    {"verb": "view", "name": "Ver cosas"},
                    {
                        "verb": "edit",
                        "name": "Editar cosas",
                        "description": "Cambia una cosa",
                    },
                ],
            }
        ],
        "deactivate_missing": False,
    }


async def test_sync_catalog_refuses_when_tags_undeclared(auth: LeoAuth) -> None:
    auth.require_action("app.things.delete")
    with pytest.raises(CatalogMismatchError):
        await auth.sync_catalog()


def test_catalog_validations() -> None:
    catalog = Catalog("app")
    with pytest.raises(ValueError):
        catalog.action("nomodule", "view", "Ver")
    catalog.module("m", "Módulo")
    with pytest.raises(ValueError):
        catalog.action("m", "Bad_Verb", "Ver")
    with pytest.raises(ValueError):
        catalog.action("m", "view", "   ")
    catalog.action("m", "view", "Ver")
    with pytest.raises(ValueError):
        catalog.action("m", "view", "Ver otra vez")


def test_catalog_action_decorator_keeps_function() -> None:
    catalog = Catalog("app")
    catalog.module("m", "Módulo")

    @catalog.action("m", "view", "Ver")
    def handler() -> int:
        return 7

    assert handler() == 7 and catalog.tags == {"app.m.view"}


# --- AuditClient ---


def make_user(token: str = "tok", jkt: str = "J" * 43) -> LeoUser:
    return LeoUser(
        id=UUID(int=5),
        username="ana",
        name="Ana",
        email="a@x",
        permissions=frozenset(),
        session_id=UUID(int=6),
        access_token=token,
        jkt=jkt,
    )


@pytest.fixture
def audit(auth: LeoAuth) -> AuditClient:
    return auth.audit


async def test_audit_record_sends_actor_and_scrubs_changes(
    audit: AuditClient, leo: FakeLeo
) -> None:
    ok = await audit.record(
        "app.things.edit",
        entity_type="thing",
        entity_id="7",
        changes={"name": {"before": "a", "after": "b"}, "password": {"after": "p"}},
        actor=make_user(),
        reason="edición",
    )
    assert ok
    event = leo.events[-1]
    assert event["actor"] == {"access_token": "tok", "jkt": "J" * 43}
    assert event["changes"] == {"name": {"before": "a", "after": "b"}}
    assert "p" not in json.dumps(event["changes"])


async def test_audit_network_failure_queues_and_retries(
    audit: AuditClient, leo: FakeLeo
) -> None:
    leo.down = True
    assert await audit.record("app.things.edit", actor=make_user()) is False
    assert audit.pending == 1
    leo.down = False
    assert await audit.record("app.things.view") is True
    assert audit.pending == 0
    assert [e["action_tag"] for e in leo.events] == [
        "app.things.edit",
        "app.things.view",
    ]
    queued = leo.events[0]
    assert "actor" not in queued and queued["actor_user_id"] == str(UUID(int=5))


async def test_audit_queue_is_bounded(auth: LeoAuth, leo: FakeLeo) -> None:
    small = AuditClient(auth.client, queue_size=2)
    leo.down = True
    for _ in range(5):
        await small.record("app.things.view")
    assert small.pending == 2


async def test_audit_invalid_actor_falls_back_to_user_id(
    audit: AuditClient, leo: FakeLeo
) -> None:
    leo.reject_actor = True
    assert await audit.record("app.things.edit", actor=make_user()) is True
    assert leo.events[-1]["actor_user_id"] == str(UUID(int=5))


async def test_audit_rejection_does_not_raise(audit: AuditClient, leo: FakeLeo) -> None:
    async def reject(_: httpx.Request) -> httpx.Response:
        return leo.err(403, "foreign_action_tag")

    client = LeoClient(
        audit._client.settings,
        http=httpx.AsyncClient(transport=httpx.MockTransport(reject)),
    )
    assert await AuditClient(client).record("other.mod.view") is False


async def test_audit_rejects_malformed_tag(audit: AuditClient) -> None:
    from leo_sdk import InvalidTagError

    with pytest.raises(InvalidTagError):
        await audit.record("bad tag")
