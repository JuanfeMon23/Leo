"""Protocolo completo para las apps: authorize -> token -> introspect ->
refresh (rotacion y reuso) -> inactividad -> logout unico; y los ataques
que cada paso debe frenar."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select, text

from app.conftest import login_as
from app.core import clock
from app.core.crypto import sha256_hex
from app.core.tests.dpop_keys import DpopKey
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import Session
from app.testkit import (
    ClientCredentials,
    grant,
    make_client_app,
    make_role,
    make_user,
    pkce_pair,
)

AUTHORIZE = "/api/v1/auth/authorize"
TOKEN = "/api/v1/auth/token"
INTROSPECT = "/api/v1/auth/introspect"
REVOKE = "/api/v1/auth/revoke"


class Flow:
    """Una app (`vlad`), un usuario con rol en ella y su navegador en Leo."""

    def __init__(
        self, session, client, nav, app: ClientCredentials, user, role
    ) -> None:
        self.session, self.client, self.nav = session, client, nav
        self.app, self.user, self.role = app, user, role
        self.device = DpopKey()  # llave del navegador en el origen de la app
        self.verifier, self.challenge = pkce_pair()

    @property
    def redirect_uri(self) -> str:
        return self.app.app.redirect_uris[0]

    async def authorize(self, **overrides) -> "object":
        body = {
            "client_id": self.app.client_id,
            "redirect_uri": self.redirect_uri,
            "state": "estado-123",
            "code_challenge": self.challenge,
            "dpop_jkt": self.device.jkt,
            **overrides,
        }
        return await self.nav.post(AUTHORIZE, json=body)

    async def code(self) -> str:
        response = await self.authorize()
        assert response.status_code == 200, response.text
        query = parse_qs(urlsplit(response.json()["redirect_to"]).query)
        assert query["state"] == ["estado-123"]
        return query["code"][0]

    async def token(
        self, body: dict, creds: ClientCredentials | None = None, secret=None
    ):
        creds = creds or self.app
        return await self.client.post(TOKEN, json=body, headers=creds.basic(secret))

    async def exchange(self, code: str, **overrides):
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": self.verifier,
            "redirect_uri": self.redirect_uri,
            "jkt": self.device.jkt,
            **overrides,
        }
        return await self.token(body)

    async def tokens(self) -> dict:
        response = await self.exchange(await self.code())
        assert response.status_code == 200, response.text
        return response.json()

    async def refresh(self, refresh_token: str, jkt: str | None = None):
        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "jkt": jkt or self.device.jkt,
        }
        return await self.token(body)

    async def introspect(self, token: str, jkt: str | None = None, creds=None) -> dict:
        creds = creds or self.app
        response = await self.client.post(
            INTROSPECT,
            json={"token": token, "jkt": jkt or self.device.jkt},
            headers=creds.basic(),
        )
        assert response.status_code == 200, response.text
        return response.json()

    async def sso(self) -> Session:
        return (
            await self.session.scalars(
                select(Session)
                .where(Session.user_id == self.user.id)
                .execution_options(populate_existing=True)
            )
        ).one()


@pytest.fixture
async def flow(session, client, make_browser) -> Flow:
    app = await make_client_app(session, slug="vlad", tags=["items.view", "items.edit"])
    role = await make_role(session, app.app.id, ["vlad.items.view"])
    user = await make_user(session)
    await grant(session, user, role)
    nav = await login_as(session, make_browser, user)
    return Flow(session, client, nav, app, user, role)


@pytest.fixture
def advance(monkeypatch):
    def move(minutes: float) -> None:
        target = clock.now() + timedelta(minutes=minutes)
        monkeypatch.setattr(clock, "now", lambda: target)

    return move


# --- flujo feliz ---


async def test_flujo_completo_authorize_token_introspect(flow: Flow):
    tokens = await flow.tokens()
    assert tokens["token_type"] == "DPoP"
    assert tokens["expires_in"] == 15 * 60
    assert tokens["access_token"] != tokens["refresh_token"]
    assert len(tokens["access_token"]) >= 43

    info = await flow.introspect(tokens["access_token"])
    assert info["active"] is True
    assert info["user"]["username"] == flow.user.username
    assert info["user"]["name"] == "Ana Gómez"
    assert info["permissions"] == ["vlad.items.view"]
    assert info["client_id"] == "vlad"
    assert info["session_id"] == str((await flow.sso()).id)


async def test_en_bd_solo_hay_hashes_de_los_tokens(flow: Flow):
    from app.testkit import COOKIE

    tokens = await flow.tokens()
    for value in (tokens["access_token"], tokens["refresh_token"]):
        found = await flow.session.scalar(
            text("SELECT count(*) FROM tokens WHERE token_hash = :v"), {"v": value}
        )
        assert found == 0
        hashed = await flow.session.scalar(
            text("SELECT count(*) FROM tokens WHERE token_hash = :h"),
            {"h": sha256_hex(value)},
        )
        assert hashed == 1
    # El secreto de la cookie SSO tampoco esta en claro: solo su hash en
    # `sessions.secret_hash`.
    cookie = flow.nav.client.cookies.get(COOKIE)
    in_clear = await flow.session.scalar(
        text(
            "SELECT (SELECT count(*) FROM sessions WHERE secret_hash = :v) "
            "+ (SELECT count(*) FROM tokens WHERE token_hash = :v)"
        ),
        {"v": cookie},
    )
    assert in_clear == 0
    assert (await flow.sso()).secret_hash == sha256_hex(cookie)


async def test_refresh_rota_y_el_viejo_ya_no_sirve(flow: Flow):
    first = await flow.tokens()
    rotated = await flow.refresh(first["refresh_token"])
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (await flow.introspect(second["access_token"]))["active"] is True


async def test_reuso_de_refresh_revoca_familia_y_sesion(flow: Flow):
    first = await flow.tokens()
    second = (await flow.refresh(first["refresh_token"])).json()

    reuse = await flow.refresh(first["refresh_token"])  # copia robada del refresh viejo

    assert reuse.status_code == 400
    assert reuse.json()["code"] == "invalid_grant"
    assert (await flow.sso()).revoked_reason == "refresh-reuse"
    assert (await flow.introspect(second["access_token"]))["active"] is False
    assert (await flow.refresh(second["refresh_token"])).status_code == 400
    assert (await flow.nav.get("/api/v1/auth/me")).status_code == 401
    event = await flow.session.scalar(
        select(AuditEvent).where(AuditEvent.action_tag == "leo.auth.refresh-reuse")
    )
    assert event is not None and event.result == "denied"


async def test_introspeccion_desliza_la_actividad(flow: Flow, advance):
    tokens = await flow.tokens()
    advance(10)
    assert (await flow.introspect(tokens["access_token"]))["active"] is True
    advance(25)  # 35 min desde el canje, 25 desde la introspeccion
    refreshed = await flow.refresh(tokens["refresh_token"])
    assert refreshed.status_code == 200, refreshed.text


async def test_inactividad_rechaza_la_introspeccion(flow: Flow, advance, monkeypatch):
    """Con la inactividad menor que la vida del access token, la
    introspeccion es la que corta y revoca la sesion."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "leo_idle_timeout_minutes", 10)
    tokens = await flow.tokens()
    advance(11)
    assert (await flow.introspect(tokens["access_token"]))["active"] is False
    assert (await flow.sso()).revoked_reason == "idle-timeout"
    assert (await flow.refresh(tokens["refresh_token"])).status_code == 400


async def test_refresh_tras_inactividad_se_rechaza(flow: Flow, advance):
    tokens = await flow.tokens()
    advance(31)
    response = await flow.refresh(tokens["refresh_token"])
    assert response.status_code == 400
    assert (await flow.sso()).revoked_reason == "idle-timeout"


async def test_access_token_expira_a_los_15_minutos(flow: Flow, advance):
    tokens = await flow.tokens()
    await flow.nav.post("/api/v1/auth/activity")
    advance(16)
    assert (await flow.introspect(tokens["access_token"]))["active"] is False


async def test_logout_unico_desde_la_app_cierra_la_sesion_sso(flow: Flow):
    tokens = await flow.tokens()
    response = await flow.client.post(
        REVOKE,
        json={"token": tokens["access_token"], "jkt": flow.device.jkt},
        headers=flow.app.basic(),
    )
    assert response.status_code == 204
    assert (await flow.sso()).revoked_reason == "logout"
    assert (await flow.nav.get("/api/v1/auth/me")).status_code == 401
    assert (await flow.introspect(tokens["access_token"]))["active"] is False


async def test_sso_segunda_app_sin_volver_a_pedir_contrasena(flow: Flow, session):
    other = await make_client_app(session, slug="incu", tags=["home.view"])
    role = await make_role(session, other.app.id, ["incu.home.view"])
    await grant(session, flow.user, role)
    await session.commit()
    response = await flow.nav.post(
        AUTHORIZE,
        json={
            "client_id": "incu",
            "redirect_uri": other.app.redirect_uris[0],
            "state": "s",
            "code_challenge": flow.challenge,
            "dpop_jkt": flow.device.jkt,
        },
    )
    assert response.status_code == 200, response.text


# --- ataques ---


async def test_code_de_un_solo_uso(flow: Flow):
    code = await flow.code()
    assert (await flow.exchange(code)).status_code == 200
    again = await flow.exchange(code)
    assert again.status_code == 400
    assert again.json()["code"] == "invalid_grant"


async def test_reuso_de_code_revoca_los_tokens_emitidos_con_el(flow: Flow):
    """Ataque (RFC 6749 4.1.2 / OAuth 2.1): el code se filtro y alguien lo
    canjea por segunda vez. Ademas de rechazarlo, los tokens que ya salieron
    de ese code (y los rotados a partir de ellos) quedan revocados."""
    code = await flow.code()
    first = await flow.exchange(code)
    assert first.status_code == 200, first.text
    first = first.json()
    rotated = await flow.refresh(first["refresh_token"])
    assert rotated.status_code == 200, rotated.text
    rotated = rotated.json()
    assert (await flow.introspect(rotated["access_token"]))["active"] is True

    again = await flow.exchange(code)

    assert again.status_code == 400
    assert again.json()["code"] == "invalid_grant"
    for access in (first["access_token"], rotated["access_token"]):
        assert (await flow.introspect(access))["active"] is False
    assert (await flow.refresh(rotated["refresh_token"])).status_code == 400
    sso = await flow.sso()
    event = await flow.session.scalar(
        select(AuditEvent).where(
            AuditEvent.action_tag == "leo.auth.token",
            AuditEvent.result == "denied",
            AuditEvent.session_id == sso.id,
            AuditEvent.reason.like("Reúso de authorization code%"),
        )
    )
    assert event is not None


async def test_reuso_de_code_por_otro_cliente_tambien_revoca(flow: Flow, session):
    """El code filtrado lo presenta otra app: igual se revocan los tokens."""
    thief = await make_client_app(session)
    await session.commit()
    code = await flow.code()
    tokens = (await flow.exchange(code)).json()
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": flow.verifier,
        "redirect_uri": flow.redirect_uri,
        "jkt": flow.device.jkt,
    }
    assert (await flow.token(body, creds=thief)).status_code == 400
    assert (await flow.introspect(tokens["access_token"]))["active"] is False


async def test_code_verifier_incorrecto_quema_el_code(flow: Flow):
    code = await flow.code()
    other_verifier, _ = pkce_pair()
    assert (await flow.exchange(code, code_verifier=other_verifier)).status_code == 400
    assert (await flow.exchange(code)).status_code == 400  # ya quemado


async def test_code_con_otro_jkt_se_rechaza(flow: Flow):
    code = await flow.code()
    assert (await flow.exchange(code, jkt=DpopKey().jkt)).status_code == 400


async def test_code_con_otra_redirect_uri_se_rechaza(flow: Flow):
    code = await flow.code()
    response = await flow.exchange(code, redirect_uri="https://evil.test/callback")
    assert response.status_code == 400


async def test_code_canjeado_por_otro_cliente_se_rechaza(flow: Flow, session):
    thief = await make_client_app(session)
    await session.commit()
    code = await flow.code()
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": flow.verifier,
        "redirect_uri": flow.redirect_uri,
        "jkt": flow.device.jkt,
    }
    assert (await flow.token(body, creds=thief)).status_code == 400


async def test_code_expirado_se_rechaza(flow: Flow, session):
    code = await flow.code()
    await session.execute(
        text(
            "UPDATE authorization_codes SET created_at = now() - interval '2 minutes', "
            "expires_at = now() - interval '61 seconds'"
        )
    )
    await session.commit()
    assert (await flow.exchange(code)).status_code == 400


async def test_secreto_de_cliente_incorrecto_401(flow: Flow):
    code = await flow.code()
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": flow.verifier,
        "redirect_uri": flow.redirect_uri,
        "jkt": flow.device.jkt,
    }
    response = await flow.token(body, secret="no-es-el-secreto")
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_client"
    assert response.headers["www-authenticate"].startswith("Basic")


async def test_sin_credenciales_de_cliente_401(flow: Flow):
    response = await flow.client.post(INTROSPECT, json={"token": "x", "jkt": "A" * 43})
    assert response.status_code == 401


async def test_app_desactivada_no_autentica(flow: Flow, session):
    flow.app.app.is_active = False
    await session.commit()
    response = await flow.client.post(
        INTROSPECT, json={"token": "x", "jkt": "A" * 43}, headers=flow.app.basic()
    )
    assert response.status_code == 401


async def test_redirect_uri_no_registrada_400(flow: Flow):
    response = await flow.authorize(redirect_uri="https://vlad.test/callback/otro")
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_redirect_uri"


async def test_cliente_inexistente_400(flow: Flow):
    response = await flow.authorize(client_id="no-existe")
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_client"


async def test_pkce_plain_no_se_acepta(flow: Flow):
    response = await flow.authorize(code_challenge_method="plain")
    assert response.status_code == 422


async def test_authorize_sin_acceso_a_la_app_403_y_auditado(flow: Flow, session):
    other = await make_client_app(session, slug="tauro")
    await session.commit()
    response = await flow.nav.post(
        AUTHORIZE,
        json={
            "client_id": "tauro",
            "redirect_uri": other.app.redirect_uris[0],
            "state": "s",
            "code_challenge": flow.challenge,
            "dpop_jkt": flow.device.jkt,
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "access_denied"
    event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action_tag == "leo.auth.authorize", AuditEvent.result == "denied"
        )
    )
    assert event is not None and event.actor_user_id == flow.user.id


async def test_authorize_sin_sesion_401(flow: Flow, browser):
    response = await browser.post(
        AUTHORIZE,
        json={
            "client_id": "vlad",
            "redirect_uri": flow.redirect_uri,
            "state": "s",
            "code_challenge": flow.challenge,
            "dpop_jkt": flow.device.jkt,
        },
    )
    assert response.status_code == 401


async def test_token_robado_sin_la_llave_introspecta_inactivo(flow: Flow):
    tokens = await flow.tokens()
    assert (await flow.introspect(tokens["access_token"], jkt=DpopKey().jkt))[
        "active"
    ] is False


async def test_introspeccion_por_otra_app_inactivo(flow: Flow, session):
    other = await make_client_app(session)
    await session.commit()
    tokens = await flow.tokens()
    assert (await flow.introspect(tokens["access_token"], creds=other))[
        "active"
    ] is False


async def test_refresh_robado_sin_la_llave_se_rechaza(flow: Flow):
    tokens = await flow.tokens()
    assert (
        await flow.refresh(tokens["refresh_token"], jkt=DpopKey().jkt)
    ).status_code == 400
    # el legitimo sigue funcionando
    assert (await flow.refresh(tokens["refresh_token"])).status_code == 200


async def test_access_token_no_sirve_como_refresh(flow: Flow):
    tokens = await flow.tokens()
    assert (await flow.refresh(tokens["access_token"])).status_code == 400


async def test_usuario_desactivado_invalida_tokens_de_inmediato(flow: Flow, admin):
    tokens = await flow.tokens()
    assert (
        await admin.post(f"/api/v1/users/{flow.user.id}/deactivate")
    ).status_code == 200
    assert (await flow.introspect(tokens["access_token"]))["active"] is False
    assert (await flow.refresh(tokens["refresh_token"])).status_code == 400


async def test_perder_el_rol_quita_el_acceso(flow: Flow, admin):
    tokens = await flow.tokens()
    response = await admin.delete(f"/api/v1/users/{flow.user.id}/roles/{flow.role.id}")
    assert response.status_code == 200, response.text
    assert (await flow.introspect(tokens["access_token"]))["active"] is False
    assert (await flow.refresh(tokens["refresh_token"])).status_code == 400


async def test_permisos_en_vivo_al_desactivar_una_accion(flow: Flow, admin, session):
    tokens = await flow.tokens()
    detail = (await admin.get(f"/api/v1/applications/{flow.app.app.id}")).json()
    action = next(
        a
        for m in detail["modules"]
        for a in m["actions"]
        if a["tag"] == "vlad.items.view"
    )
    url = f"/api/v1/applications/{flow.app.app.id}/actions/{action['id']}/deactivate"
    assert (await admin.post(url)).status_code == 200
    info = await flow.introspect(tokens["access_token"])
    assert info["active"] is True and info["permissions"] == []


async def test_sso_cookie_de_leo_no_es_un_token_de_la_app(flow: Flow, session):
    """El token SSO (cookie) es de la app `leo`: introspectarlo como `vlad`
    da inactivo aunque se conozca el jkt."""
    from app.testkit import COOKIE

    cookie = flow.nav.client.cookies.get(COOKIE)
    assert (await flow.introspect(cookie, jkt=flow.nav.key.jkt))["active"] is False


# --- introspect: nombre, aplicaciones accesibles y actividad ---


async def test_introspect_trae_nombre_apellido_aplicaciones_y_actividad(flow: Flow):
    from datetime import datetime

    tokens = await flow.tokens()
    info = await flow.introspect(tokens["access_token"])

    assert info["user"]["first_name"] == "Ana"
    assert info["user"]["last_name"] == "Gómez"
    assert info["user"]["name"] == "Ana Gómez"
    assert info["applications"] == [
        {"slug": "vlad", "name": "App vlad", "base_url": "https://vlad.test"}
    ]
    last = datetime.fromisoformat(info["last_activity_at"])
    assert last.tzinfo is not None
    assert last == (await flow.sso()).last_activity_at


async def test_introspect_last_activity_at_ya_viene_deslizado(flow: Flow, advance):
    from datetime import datetime

    tokens = await flow.tokens()
    before = (await flow.sso()).last_activity_at
    advance(10)
    info = await flow.introspect(tokens["access_token"])
    after = datetime.fromisoformat(info["last_activity_at"])
    assert after == clock.now() and after > before


async def test_introspect_applications_solo_las_apps_con_acceso(flow: Flow, session):
    other = await make_client_app(session, slug="incu", tags=["home.view"])
    role = await make_role(session, other.app.id, ["incu.home.view"])
    await grant(session, flow.user, role)
    # app con rol pero desactivada, app activa sin rol, rol inactivo
    off = await make_client_app(session, slug="off", tags=["home.view"])
    off_role = await make_role(session, off.app.id, ["off.home.view"])
    await grant(session, flow.user, off_role)
    off.app.is_active = False
    await make_client_app(session, slug="sinrol", tags=["home.view"])
    dead = await make_client_app(session, slug="muerta", tags=["home.view"])
    dead_role = await make_role(
        session, dead.app.id, ["muerta.home.view"], is_active=False
    )
    await grant(session, flow.user, dead_role)
    await session.flush()

    info = await flow.introspect((await flow.tokens())["access_token"])

    assert sorted(a["slug"] for a in info["applications"]) == ["incu", "vlad"]
    assert all(set(a) == {"slug", "name", "base_url"} for a in info["applications"])


async def test_introspect_inactivo_no_trae_los_campos_nuevos(flow: Flow):
    info = await flow.introspect("x" * 43)
    assert info == {"active": False}


async def test_introspect_no_filtra_campos_sensibles(flow: Flow):
    info = await flow.introspect((await flow.tokens())["access_token"])
    assert set(info) == {
        "active",
        "principal_type",
        "user",
        "permissions",
        "session_id",
        "client_id",
        "exp",
        "idle_timeout_seconds",
        "applications",
        "last_activity_at",
    }
    assert set(info["user"]) == {
        "id",
        "username",
        "name",
        "first_name",
        "last_name",
        "email",
    }
    raw = str(info)
    for secret in (flow.app.secret, "secret_hash", "client_secret", "password"):
        assert secret not in raw
