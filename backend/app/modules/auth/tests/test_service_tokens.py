"""Credenciales de servicio (OAuth 2.0 client credentials): una app llamadora
(`incubus`) pide un token para consultar a otra (`vlad`, la audiencia), que
lo valida contra Leo con `/introspect`. Incluye los ataques que cada paso
debe frenar."""

from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.conftest import login_as
from app.core import clock
from app.core.crypto import sha256_hex
from app.core.tests.dpop_keys import DpopKey
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import ServiceToken
from app.testkit import (
    COOKIE,
    grant_service_access,
    make_client_app,
    make_role,
    make_user,
    set_setting,
)

TOKEN = "/api/v1/auth/token"
INTROSPECT = "/api/v1/auth/introspect"
ME = "/api/v1/auth/me"


class Services:
    """`incubus` (llamadora) con un rol de `vlad` (audiencia) concedido."""

    def __init__(self, session, client, caller, audience, role) -> None:
        self.session, self.client = session, client
        self.caller, self.audience, self.role = caller, audience, role

    async def issue(self, audience: str | None = None, creds=None, secret=None):
        creds = creds or self.caller
        body = {
            "grant_type": "client_credentials",
            "audience": audience or self.audience.client_id,
        }
        return await self.client.post(TOKEN, json=body, headers=creds.basic(secret))

    async def token(self) -> str:
        response = await self.issue()
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    async def introspect(self, token: str, creds=None, **extra):
        creds = creds or self.audience
        response = await self.client.post(
            INTROSPECT, json={"token": token, **extra}, headers=creds.basic()
        )
        return response

    async def info(self, token: str, creds=None) -> dict:
        response = await self.introspect(token, creds)
        assert response.status_code == 200, response.text
        return response.json()

    async def events(self, result: str | None = None) -> list[AuditEvent]:
        stmt = select(AuditEvent).where(
            AuditEvent.action_tag == "leo.auth.service-token"
        )
        if result:
            stmt = stmt.where(AuditEvent.result == result)
        return list((await self.session.scalars(stmt)).all())


@pytest.fixture
async def svc(session, client) -> Services:
    caller = await make_client_app(session, slug="incubus")
    audience = await make_client_app(
        session,
        slug="vlad",
        tags=["catalog.view", "samples.view", "samples.edit"],
    )
    role = await make_role(
        session, audience.app.id, ["vlad.catalog.view", "vlad.samples.view"]
    )
    await grant_service_access(session, caller.app, role)
    await session.commit()
    return Services(session, client, caller, audience, role)


@pytest.fixture
def advance(monkeypatch):
    def move(minutes: float) -> None:
        target = clock.now() + timedelta(minutes=minutes)
        monkeypatch.setattr(clock, "now", lambda: target)

    return move


# --- emision ---


async def test_emision_feliz(svc: Services):
    response = await svc.issue()
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in", "audience"}
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 600
    assert body["audience"] == "vlad"
    assert len(body["access_token"]) >= 43
    assert response.headers["cache-control"] == "no-store"
    assert "refresh_token" not in body


async def test_cada_emision_da_un_token_distinto(svc: Services):
    assert await svc.token() != await svc.token()


async def test_el_token_solo_se_guarda_como_hash(svc: Services, session):
    token = await svc.token()
    row = (await session.scalars(select(ServiceToken))).one()
    assert row.token_hash == sha256_hex(token)
    assert row.caller_application_id == svc.caller.app.id
    assert row.audience_application_id == svc.audience.app.id
    for table in ("service_tokens", "audit_events", "tokens", "sessions"):
        dump = await session.scalar(
            text(f"SELECT string_agg(t::text, ' ') FROM {table} t")
        )
        assert token not in (dump or "")


async def test_emision_auditada_sin_el_token(svc: Services):
    token = await svc.token()
    (event,) = await svc.events("ok")
    assert event.entity_id == str(svc.caller.app.id)
    assert event.changes["audience"] == {"before": None, "after": "vlad"}
    assert "expires_at" in event.changes
    assert token not in str(event.changes) + (event.reason or "")
    assert not any("token" in key or "hash" in key for key in event.changes)


async def test_la_vida_es_configurable_con_tope_de_una_hora(svc: Services, session):
    from app.core.runtime_settings import LEO_SETTINGS

    await set_setting(session, "auth.service_token_minutes", 60)
    assert (await svc.issue()).json()["expires_in"] == 3600
    await set_setting(session, "auth.service_token_minutes", 3)
    assert (await svc.issue()).json()["expires_in"] == 180
    assert LEO_SETTINGS.get("auth.service_token_minutes").max == 60


async def test_sin_concesion_se_deniega_y_se_audita(svc: Services, session):
    other = await make_client_app(session, slug="taurus")
    await session.commit()
    response = await svc.issue(creds=other)
    assert response.status_code == 403
    assert response.json()["code"] == "access_denied"
    assert "vlad" in response.json()["message"]
    assert "access_token" not in response.text
    (event,) = await svc.events("denied")
    assert event.entity_id == str(other.app.id)
    assert await svc.events("ok") == []
    assert (await session.scalars(select(ServiceToken))).all() == []


async def test_concesion_con_rol_inactivo_no_alcanza(svc: Services, session):
    svc.role.is_active = False
    await session.commit()
    response = await svc.issue()
    assert response.status_code == 403
    assert response.json()["code"] == "access_denied"
    assert len(await svc.events("denied")) == 1


async def test_concesion_a_otra_audiencia_no_sirve_para_esta(svc: Services, session):
    third = await make_client_app(session, slug="acuarius", tags=["x.view"])
    await session.commit()
    response = await svc.issue(audience=third.client_id)
    assert response.status_code == 403


async def test_audiencia_igual_a_la_llamadora(svc: Services):
    response = await svc.issue(audience="incubus")
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_target"
    assert len(await svc.events("denied")) == 1


async def test_audiencia_inexistente(svc: Services):
    response = await svc.issue(audience="no-existe")
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_target"
    assert len(await svc.events("denied")) == 1


async def test_audiencia_desactivada(svc: Services, session):
    svc.audience.app.is_active = False
    await session.commit()
    response = await svc.issue()
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_target"


async def test_llamadora_desactivada_no_autentica(svc: Services, session):
    svc.caller.app.is_active = False
    await session.commit()
    response = await svc.issue()
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_client"


async def test_secreto_incorrecto_401(svc: Services):
    response = await svc.issue(secret="no-es-el-secreto")
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_client"
    assert response.headers["www-authenticate"].startswith("Basic")


async def test_sin_credenciales_401(svc: Services):
    response = await svc.client.post(
        TOKEN, json={"grant_type": "client_credentials", "audience": "vlad"}
    )
    assert response.status_code == 401


async def test_audience_es_obligatoria(svc: Services):
    response = await svc.client.post(
        TOKEN,
        json={"grant_type": "client_credentials"},
        headers=svc.caller.basic(),
    )
    assert response.status_code == 422


async def test_no_acepta_campos_extra_ni_jkt(svc: Services):
    response = await svc.client.post(
        TOKEN,
        json={
            "grant_type": "client_credentials",
            "audience": "vlad",
            "jkt": DpopKey().jkt,
        },
        headers=svc.caller.basic(),
    )
    assert response.status_code == 422


async def test_rate_limit_por_cliente(svc: Services, session):
    await set_setting(session, "rate_limit.service_token_per_window", 5)
    for _ in range(5):
        assert (await svc.issue()).status_code == 200
    third = await svc.issue()
    assert third.status_code == 429
    assert third.json()["code"] == "too_many_attempts"
    assert int(third.headers["retry-after"]) >= 1
    # otro cliente no se ve afectado
    other = await make_client_app(session, slug="taurus")
    await session.commit()
    assert (await svc.issue(creds=other)).status_code == 403


# --- introspeccion ---


async def test_introspeccion_por_la_audiencia(svc: Services):
    token = await svc.token()
    info = await svc.info(token)
    assert info["active"] is True
    assert set(info) == {"active", "principal_type", "client", "permissions", "exp"}
    assert info["principal_type"] == "service"
    assert info["client"] == {"client_id": "incubus", "name": "App incubus"}
    assert info["permissions"] == ["vlad.catalog.view", "vlad.samples.view"]
    assert isinstance(info["exp"], int)
    assert info["exp"] == pytest.approx(clock.now().timestamp() + 600, abs=5)


async def test_introspeccion_no_necesita_jkt_pero_lo_ignora_si_llega(svc: Services):
    token = await svc.token()
    response = await svc.introspect(token, jkt=DpopKey().jkt)
    assert response.status_code == 200
    assert response.json()["principal_type"] == "service"


async def test_otra_app_no_puede_validar_un_token_ajeno(svc: Services, session):
    other = await make_client_app(session, slug="taurus")
    await session.commit()
    token = await svc.token()
    assert await svc.info(token, creds=other) == {"active": False}
    # ni siquiera la propia llamadora
    assert await svc.info(token, creds=svc.caller) == {"active": False}


async def test_token_desconocido_sin_jkt_se_rechaza(svc: Services):
    # sin jkt y sin ser de servicio: se exige jkt (como en un token de usuario)
    response = await svc.introspect("x" * 43)
    assert response.status_code == 422


async def test_permisos_solo_acciones_activas_de_roles_activos(svc: Services, session):
    from app.modules.applications.models import Action

    token = await svc.token()
    # rol activo adicional con una accion; rol inactivo con otra
    extra = await make_role(session, svc.audience.app.id, ["vlad.samples.edit"])
    dead = await make_role(session, svc.audience.app.id, [], is_active=False)
    await grant_service_access(session, svc.caller.app, extra)
    await grant_service_access(session, svc.caller.app, dead)
    await session.commit()
    assert (await svc.info(token))["permissions"] == [
        "vlad.catalog.view",
        "vlad.samples.edit",
        "vlad.samples.view",
    ]
    action = await session.scalar(
        select(Action).where(Action.tag == "vlad.samples.view")
    )
    action.is_active = False
    await session.commit()
    assert (await svc.info(token))["permissions"] == [
        "vlad.catalog.view",
        "vlad.samples.edit",
    ]


async def test_modulo_desactivado_no_aporta_permisos(svc: Services, session):
    from app.modules.applications.models import AppModule

    token = await svc.token()
    module = await session.scalar(
        select(AppModule).where(
            AppModule.application_id == svc.audience.app.id,
            AppModule.slug == "samples",
        )
    )
    module.is_active = False
    await session.commit()
    assert (await svc.info(token))["permissions"] == ["vlad.catalog.view"]


async def test_permisos_solo_de_la_audiencia_del_token(svc: Services, session):
    third = await make_client_app(session, slug="acuarius", tags=["x.view"])
    other_role = await make_role(session, third.app.id, ["acuarius.x.view"])
    await grant_service_access(session, svc.caller.app, other_role)
    await session.commit()
    info = await svc.info(await svc.token())
    assert all(tag.startswith("vlad.") for tag in info["permissions"])


async def test_roles_desactivados_dejan_el_token_inactivo(svc: Services, session):
    token = await svc.token()
    svc.role.is_active = False
    await session.commit()
    assert await svc.info(token) == {"active": False}


async def test_quitar_la_concesion_se_refleja_de_inmediato(svc: Services, session):
    from app.modules.roles.models import ServiceGrant

    token = await svc.token()
    await session.execute(
        ServiceGrant.__table__.delete().where(
            ServiceGrant.caller_application_id == svc.caller.app.id
        )
    )
    assert await svc.info(token) == {"active": False}


async def test_token_expirado_es_inactivo(svc: Services, advance):
    token = await svc.token()
    advance(9)
    assert (await svc.info(token))["active"] is True
    advance(10.5)
    assert await svc.info(token) == {"active": False}


async def test_token_revocado_es_inactivo(svc: Services, session):
    token = await svc.token()
    row = (await session.scalars(select(ServiceToken))).one()
    row.revoked_at = clock.now()
    await session.commit()
    assert await svc.info(token) == {"active": False}


async def test_desactivar_la_llamadora_invalida_sus_tokens(
    svc: Services, admin, session
):
    token = await svc.token()
    await session.commit()
    response = await admin.post(f"/api/v1/applications/{svc.caller.app.id}/deactivate")
    assert response.status_code == 200, response.text
    assert await svc.info(token) == {"active": False}


async def test_desactivar_la_audiencia_invalida_los_tokens(
    svc: Services, admin, session
):
    token = await svc.token()
    await session.commit()
    response = await admin.post(
        f"/api/v1/applications/{svc.audience.app.id}/deactivate"
    )
    assert response.status_code == 200, response.text
    # la audiencia desactivada ni siquiera se autentica para preguntar
    assert (await svc.introspect(token)).status_code == 401
    # y nadie obtiene tokens nuevos para ella
    assert (await svc.issue()).status_code == 400


async def test_audiencia_desactivada_introspeccion_directa(svc: Services, session):
    token = await svc.token()
    svc.audience.app.is_active = False
    await session.commit()
    assert (await svc.introspect(token)).status_code == 401
    svc.audience.app.is_active = True
    await session.commit()
    assert (await svc.info(token))["active"] is True


# --- el token de servicio no sirve como credencial de usuario (y viceversa) ---


async def test_token_de_servicio_no_es_cookie_sso(svc: Services, make_browser):
    token = await svc.token()
    nav = make_browser()
    response = await nav.get(ME, headers={"Cookie": f"{COOKIE}={token}"})
    assert response.status_code == 401


async def test_token_de_servicio_no_abre_endpoints_de_usuario_ni_admin(
    svc: Services, make_browser
):
    token = await svc.token()
    nav = make_browser()
    for path in (ME, "/api/v1/applications", "/api/v1/users", "/api/v1/roles"):
        bearer = await nav.get(path, headers={"Authorization": f"Bearer {token}"})
        assert bearer.status_code == 401, path
        dpop = await nav.get(path, headers={"Authorization": f"DPoP {token}"})
        assert dpop.status_code == 401, path
        cookie = await nav.get(path, headers={"Cookie": f"{COOKIE}={token}"})
        assert cookie.status_code == 401, path


async def test_token_de_servicio_no_sirve_en_revoke_ni_refresh(svc: Services):
    token = await svc.token()
    jkt = DpopKey().jkt
    revoke = await svc.client.post(
        "/api/v1/auth/revoke",
        json={"token": token, "jkt": jkt},
        headers=svc.audience.basic(),
    )
    assert revoke.status_code == 204
    assert (await svc.info(token))["active"] is True  # no lo revoca
    refresh = await svc.client.post(
        TOKEN,
        json={"grant_type": "refresh_token", "refresh_token": token, "jkt": jkt},
        headers=svc.caller.basic(),
    )
    assert refresh.status_code == 400


async def test_token_de_usuario_no_es_token_de_servicio(
    svc: Services, session, make_browser
):
    """Un access token de usuario introspectado sin jkt (la forma de servicio)
    no se acepta: el jkt sigue siendo obligatorio para tokens de usuario."""
    from app.modules.auth.tests.test_oauth_flow import Flow
    from app.testkit import grant

    user = await make_user(session)
    await grant(session, user, await make_role(session, svc.audience.app.id, []))
    nav = await login_as(session, make_browser, user)
    flow = Flow(session, svc.client, nav, svc.audience, user, svc.role)
    tokens = await flow.tokens()
    sin_jkt = await svc.introspect(tokens["access_token"])
    assert sin_jkt.status_code == 422
    assert "access_token" not in sin_jkt.text
    con_jkt = await flow.introspect(tokens["access_token"])
    assert con_jkt["active"] is True
    assert con_jkt["principal_type"] == "user"


async def test_jkt_obligatorio_en_revoke(svc: Services):
    response = await svc.client.post(
        "/api/v1/auth/revoke",
        json={"token": "x" * 43},
        headers=svc.audience.basic(),
    )
    assert response.status_code == 422


async def test_clientes_no_pueden_pedir_token_para_otro(svc: Services, session):
    """El `client_id` del que pide sale de las credenciales, nunca del cuerpo."""
    response = await svc.client.post(
        TOKEN,
        json={
            "grant_type": "client_credentials",
            "audience": "vlad",
            "client_id": "taurus",
        },
        headers=svc.caller.basic(),
    )
    assert response.status_code == 422
