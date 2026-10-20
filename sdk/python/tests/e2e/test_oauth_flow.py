"""E2E: el SDK contra la app REAL de Leo (cierra el pendiente "prueba real del
flujo OAuth").

Recorre: sync de catalogo -> login SSO de un usuario con rol -> authorize (lo
que hace el frontend de Leo) -> callback/canje -> introspect (permisos de ESA
app) -> require_action permitido y 403 -> heartbeat -> refresh y reuso ->
logout unico -> introspect inactivo -> ingesta de auditoria. Mas el caso de la
cookie robada sin llave.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from app.testkit import (
    Browser as LeoBrowser,
)
from app.testkit import (
    grant,
    make_client_app,
    make_role,
    make_user,
    unique,
)
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from leo_sdk import (
    Catalog,
    LeoAuth,
    LeoClient,
    LeoSettings,
    LeoUser,
    leo_router,
)
from leo_sdk.errors import InvalidGrantError
from tests.helpers import DpopKey

LEO_PUBLIC = "https://leo.test"


@dataclass
class AppHarness:
    slug: str
    secret: str
    auth: LeoAuth
    fastapi: FastAPI
    app_id: object
    redirect_uri: str
    public_url: str


class AppBrowser:
    """Navegador del usuario frente al BFF de la app (llave DPoP propia)."""

    def __init__(self, harness: AppHarness, key: DpopKey | None = None) -> None:
        self.h = harness
        self.key = key or DpopKey()
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=harness.fastapi),
            base_url=harness.public_url,
        )

    async def call(
        self, method: str, path: str, *, proof: bool = True, **kwargs
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if proof:
            url = self.h.public_url + path.split("?")[0]
            headers["DPoP"] = self.key.proof(method, url)
        return await self.http.request(method, path, headers=headers, **kwargs)


def build_catalog(slug: str) -> Catalog:
    catalog = Catalog(slug)
    catalog.module("things", "Cosas", "Gestión de cosas")
    catalog.action("things", "view", "Ver cosas")
    catalog.action("things", "edit", "Editar cosas", "Modifica una cosa")
    return catalog


@pytest_asyncio.fixture
async def harness(
    session: AsyncSession, make_browser: Callable[[], LeoBrowser]
) -> AppHarness:
    """App cliente registrada en Leo + su backend FastAPI con el SDK, que habla
    con la app REAL de Leo (transporte ASGI)."""
    slug = unique("e2e")
    creds = await make_client_app(session, slug=slug)
    public_url = f"https://{slug}.test"
    settings = LeoSettings(
        leo_url="https://admin.leo.test",
        leo_api_url=f"{LEO_PUBLIC}/api/v1",
        app_client_id=slug,
        app_client_secret=creds.secret,
        public_url=public_url,
        redirect_uri=creds.app.redirect_uris[0],
    )
    # El cliente HTTP del SDK usa la misma sesion de BD de la prueba.
    leo_http = make_browser().client
    auth = LeoAuth(
        settings,
        catalog=build_catalog(slug),
        client=LeoClient(settings, http=leo_http),
    )
    application = FastAPI()
    auth.install(application)
    application.include_router(leo_router(auth))
    view = Annotated[LeoUser, auth.require_action(f"{slug}.things.view")]
    edit = Annotated[LeoUser, auth.require_action(f"{slug}.things.edit")]

    @application.get("/things")
    async def list_things(user: view) -> dict:
        return {"user": user.username}

    @application.post("/things")
    async def change_thing(user: edit) -> dict:
        return {"ok": True}

    return AppHarness(
        slug=slug,
        secret=creds.secret,
        auth=auth,
        fastapi=application,
        app_id=creds.app.id,
        redirect_uri=creds.app.redirect_uris[0],
        public_url=public_url,
    )


@pytest_asyncio.fixture
async def logged_in(
    harness: AppHarness,
    session: AsyncSession,
    make_browser: Callable[[], LeoBrowser],
):
    """Sync de catalogo + usuario con rol `things.view` + SSO + flujo completo
    hasta tener cookies en el navegador de la app."""
    await harness.auth.sync_catalog()
    user = await make_user(session)
    role = await make_role(
        session, harness.app_id, tags=[f"{harness.slug}.things.view"]
    )
    await grant(session, user, role)
    await session.commit()

    leo_browser = make_browser()  # navegador en el origen de Leo (SSO)
    assert (await leo_browser.login(user.username)).status_code == 200

    app_browser = AppBrowser(harness)
    started = await app_browser.call("GET", "/auth/login")
    assert started.status_code == 200, started.text
    query = parse_qs(urlsplit(started.json()["authorize_url"]).query)
    assert query["dpop_jkt"][0] == app_browser.key.jkt
    # Lo que hace la pantalla authorize del frontend de Leo con la sesion SSO.
    authorized = await leo_browser.post(
        "/api/v1/auth/authorize",
        json={
            "client_id": query["client_id"][0],
            "redirect_uri": query["redirect_uri"][0],
            "state": query["state"][0],
            "code_challenge": query["code_challenge"][0],
            "code_challenge_method": "S256",
            "dpop_jkt": query["dpop_jkt"][0],
        },
    )
    assert authorized.status_code == 200, authorized.text
    redirect = parse_qs(urlsplit(authorized.json()["redirect_to"]).query)
    callback = await app_browser.call(
        "GET",
        f"/auth/callback?code={redirect['code'][0]}&state={redirect['state'][0]}",
    )
    assert callback.status_code == 200, callback.text
    return user, leo_browser, app_browser, callback


async def test_catalog_check_is_clean(harness: AppHarness) -> None:
    harness.auth.check_catalog()


async def test_full_flow(
    harness: AppHarness, logged_in, make_browser: Callable[[], LeoBrowser], admin
) -> None:
    user, _leo_browser, app_browser, callback = logged_in
    auth = harness.auth

    # callback: cookies HttpOnly en el dominio de la app; ningun token en el cuerpo
    assert callback.json()["user"]["username"] == user.username
    assert callback.json()["user"]["permissions"] == [f"{harness.slug}.things.view"]
    access = app_browser.http.cookies["__Host-leo_access"]
    refresh = app_browser.http.cookies["__Host-leo_refresh"]
    assert access not in callback.text and refresh not in callback.text
    set_cookies = "\n".join(callback.headers.get_list("set-cookie")).lower()
    assert "httponly" in set_cookies and "samesite=strict" in set_cookies

    # introspect directo (permisos de ESTA app, ligado al jkt del navegador)
    jkt = app_browser.key.jkt
    intro = await auth.client.introspect(access, jkt)
    assert intro.active and intro.permissions == [f"{harness.slug}.things.view"]
    assert (await auth.client.introspect(access, DpopKey().jkt)).active is False

    # require_action: permitido y 403 (+ evento denied en la auditoria de Leo)
    assert (await app_browser.call("GET", "/things")).json() == {"user": user.username}
    denied = await app_browser.call("POST", "/things")
    assert denied.status_code == 403 and denied.json()["code"] == "forbidden"
    events = await admin.get(
        f"/api/v1/audit/events?action_tag={harness.slug}.things.edit&result=denied"
    )
    assert events.status_code == 200, events.text
    items = events.json()["items"]
    assert len(items) == 1 and items[0]["actor_username"] == user.username

    # heartbeat (introspect sin cache)
    assert (await app_browser.call("POST", "/auth/activity")).status_code == 204

    # ingesta de auditoria desde la app, con diff sin campos sensibles
    changes = auth.audit.diff(
        {"name": "a", "password": "p1"}, {"name": "b", "password": "p2"}
    )
    ok = await auth.audit.record(
        f"{harness.slug}.things.view",
        entity_type="thing",
        entity_id="42",
        changes=changes,
        actor=await auth.sessions.user_for(access, jkt),
        reason="prueba e2e",
    )
    assert ok
    ingested = await admin.get(
        f"/api/v1/audit/events?action_tag={harness.slug}.things.view&result=ok"
    )
    event = ingested.json()["items"][0]
    assert event["actor_username"] == user.username
    assert event["changes"] == {"name": {"before": "a", "after": "b"}}
    assert "p1" not in str(event) and "p2" not in str(event)

    # refresh transparente: el access vence en Leo (se simula revocando su
    # cache local y usando solo el refresh)
    app_browser.http.cookies.delete("__Host-leo_access")
    auth.sessions._cache.clear()
    me = await app_browser.call("GET", "/auth/me")
    assert me.status_code == 200, me.text
    new_refresh = app_browser.http.cookies["__Host-leo_refresh"]
    assert new_refresh != refresh

    # reuso del refresh viejo -> invalid_grant y revoca familia + sesion
    with pytest.raises(InvalidGrantError):
        await auth.client.refresh(refresh, jkt)
    new_access = app_browser.http.cookies["__Host-leo_access"]
    assert (await auth.client.introspect(new_access, jkt)).active is False
    auth.sessions._cache.clear()
    dead = await app_browser.call("GET", "/auth/me")
    assert dead.status_code == 401 and dead.json()["code"] == "session_expired"


async def test_logout_is_single_and_introspect_inactive(
    harness: AppHarness, logged_in
) -> None:
    _user, leo_browser, app_browser, _ = logged_in
    access = app_browser.http.cookies["__Host-leo_access"]
    jkt = app_browser.key.jkt
    assert (await app_browser.call("GET", "/auth/me")).status_code == 200

    logout = await app_browser.call("POST", "/auth/logout")
    assert logout.status_code == 204
    assert not app_browser.http.cookies.get("__Host-leo_access")

    assert (await harness.auth.client.introspect(access, jkt)).active is False
    # logout unico: la sesion SSO de Leo tambien murio
    me = await leo_browser.get("/api/v1/auth/me")
    assert me.status_code == 401


async def test_stolen_cookie_without_key(harness: AppHarness, logged_in) -> None:
    _user, _leo_browser, victim, _ = logged_in
    access = victim.http.cookies["__Host-leo_access"]
    refresh = victim.http.cookies["__Host-leo_refresh"]

    def thief_with(key: DpopKey | None) -> AppBrowser:
        thief = AppBrowser(harness, key)
        thief.http.cookies.set(
            "__Host-leo_access", access, domain=urlsplit(harness.public_url).hostname
        )
        thief.http.cookies.set(
            "__Host-leo_refresh", refresh, domain=urlsplit(harness.public_url).hostname
        )
        return thief

    # 1) sin prueba DPoP
    no_proof = await thief_with(None).call("GET", "/things", proof=False)
    assert no_proof.status_code == 401
    assert no_proof.json()["code"] == "invalid_dpop_proof"
    # 2) con la llave propia del ladron (otro jkt): ni access ni refresh sirven
    other = await thief_with(DpopKey()).call("GET", "/things")
    assert other.status_code == 401
    assert other.json()["code"] == "session_expired"
    # 3) el dueno legitimo sigue entrando
    assert (await victim.call("GET", "/things")).status_code == 200
    # 4) replay de una prueba ya usada
    proof = victim.key.proof("GET", harness.public_url + "/things")
    assert (
        await victim.http.get("/things", headers={"DPoP": proof})
    ).status_code == 200
    assert (
        await victim.http.get("/things", headers={"DPoP": proof})
    ).status_code == 401


async def test_user_without_access_cannot_authorize(
    harness: AppHarness,
    session: AsyncSession,
    make_browser: Callable[[], LeoBrowser],
) -> None:
    user = await make_user(session)  # sin rol en la app
    await session.commit()
    leo_browser = make_browser()
    await leo_browser.login(user.username)
    app_browser = AppBrowser(harness)
    started = await app_browser.call("GET", "/auth/login")
    query = parse_qs(urlsplit(started.json()["authorize_url"]).query)
    response = await leo_browser.post(
        "/api/v1/auth/authorize",
        json={
            "client_id": query["client_id"][0],
            "redirect_uri": query["redirect_uri"][0],
            "state": query["state"][0],
            "code_challenge": query["code_challenge"][0],
            "code_challenge_method": "S256",
            "dpop_jkt": query["dpop_jkt"][0],
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "access_denied"


async def test_catalog_sync_is_idempotent_and_names_are_kept(
    harness: AppHarness, admin
) -> None:
    first = await harness.auth.sync_catalog()
    assert sorted(first["created_actions"]) == [
        f"{harness.slug}.things.edit",
        f"{harness.slug}.things.view",
    ]
    again = await harness.auth.sync_catalog()
    assert again["created_actions"] == []
