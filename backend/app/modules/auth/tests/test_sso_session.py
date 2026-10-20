"""Sesion SSO del frontend de Leo: cookie + DPoP con el jkt de la sesion,
inactividad (reloj controlable), heartbeat, logout y sesiones."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.conftest import login_as
from app.core import clock
from app.core.tests.dpop_keys import DpopKey
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import Session
from app.testkit import COOKIE, PUBLIC_URL, make_user

ME = "/api/v1/auth/me"


@pytest.fixture
def advance(monkeypatch):
    """Adelanta el reloj de la app `minutes` minutos."""

    def move(minutes: float) -> None:
        target = clock.now() + timedelta(minutes=minutes)
        monkeypatch.setattr(clock, "now", lambda: target)

    return move


async def _sso(session, user_id) -> Session:
    return (
        await session.scalars(
            select(Session)
            .where(Session.user_id == user_id)
            .execution_options(populate_existing=True)
        )
    ).one()


async def test_sin_cookie_401(browser):
    response = await browser.get(ME)
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


async def test_cookie_robada_sin_la_llave_no_sirve(admin, make_browser):
    """Ataque: el atacante copia la cookie a su navegador y firma con SU llave."""
    thief = make_browser()
    thief.client.cookies.set(
        COOKIE, admin.client.cookies.get(COOKIE), domain="leo.test"
    )
    response = await thief.get(ME)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_dpop_proof"


async def test_cookie_sin_prueba_dpop_no_sirve(admin):
    response = await admin.get(ME, dpop=False)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_dpop_proof"


async def test_prueba_dpop_reusada_se_rechaza(admin):
    proof = admin.proof("GET", ME)
    assert (await admin.get(ME, headers={"DPoP": proof})).status_code == 200
    replay = await admin.get(ME, headers={"DPoP": proof})
    assert replay.status_code == 401
    assert replay.json()["code"] == "invalid_dpop_proof"


async def test_prueba_dpop_de_otra_ruta_se_rechaza(admin):
    proof = admin.proof("GET", "/api/v1/users")
    assert (await admin.get(ME, headers={"DPoP": proof})).status_code == 401


async def test_prueba_dpop_con_metodo_cambiado_se_rechaza(admin):
    proof = admin.key.proof("POST", PUBLIC_URL + ME)
    assert (await admin.get(ME, headers={"DPoP": proof})).status_code == 401


async def test_dos_headers_dpop_se_rechazan(admin):
    headers = [("DPoP", admin.proof("GET", ME)), ("DPoP", admin.proof("GET", ME))]
    response = await admin.client.get(ME, headers=headers)
    assert response.status_code == 401


async def test_actividad_desliza_la_ventana_de_inactividad(session, admin, advance):
    advance(20)
    assert (await admin.post("/api/v1/auth/activity")).status_code == 204
    advance(20)  # 40 min desde el login, 20 desde la ultima actividad
    assert (await admin.get(ME)).status_code == 200


async def test_inactividad_mayor_al_limite_revoca_la_sesion(session, admin, advance):
    advance(31)
    response = await admin.get(ME)
    assert response.status_code == 401
    assert response.json()["code"] == "session_expired"
    sso = await _sso(session, admin.user.id)
    assert sso.revoked_reason == "idle-timeout"
    event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action_tag == "leo.auth.idle-timeout",
            AuditEvent.session_id == sso.id,
        )
    )
    assert event is not None
    advance(0)  # aun "volviendo" la sesion sigue revocada
    assert (await admin.get(ME)).status_code == 401


async def test_logout_revoca_y_borra_la_cookie(session, admin):
    response = await admin.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert COOKIE in response.headers["set-cookie"]
    assert (await _sso(session, admin.user.id)).revoked_reason == "logout"
    # aunque el atacante conservara la cookie, ya no sirve
    admin.client.cookies.set(COOKIE, "cualquiera", domain="leo.test")
    assert (await admin.get(ME)).status_code == 401


async def test_usuario_desactivado_pierde_la_sesion(session, admin, make_browser):
    other = await make_user(session)
    nav = await login_as(session, make_browser, other)
    response = await admin.post(f"/api/v1/users/{other.id}/deactivate")
    assert response.status_code == 200, response.text
    assert (await nav.get(ME)).status_code == 401
    assert (await _sso(session, other.id)).revoked_reason == "user-deactivated"


async def test_listar_sesiones_propias_marca_la_actual(admin):
    response = await admin.get("/api/v1/auth/sessions")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1 and items[0]["is_current"] is True


async def test_sesiones_requieren_permiso(session, make_browser):
    user = await make_user(session)
    nav = await login_as(session, make_browser, user)
    response = await nav.get("/api/v1/auth/sessions")
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    denied = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action_tag == "leo.auth.view",
            AuditEvent.result == "denied",
            AuditEvent.actor_user_id == user.id,
        )
    )
    assert denied is not None


async def test_admin_revoca_la_sesion_de_otro(session, admin, make_browser):
    other = await make_user(session)
    nav = await login_as(session, make_browser, other)
    sso = await _sso(session, other.id)
    response = await admin.post(f"/api/v1/auth/sessions/{sso.id}/revoke")
    assert response.status_code == 204
    assert (await nav.get(ME)).status_code == 401
    listed = await admin.get(
        f"/api/v1/auth/sessions?user_id={other.id}&active_only=false"
    )
    assert listed.json()["items"][0]["revoked_reason"] == "admin"


async def test_nueva_llave_en_el_mismo_navegador_no_reusa_la_sesion(admin):
    """Si la llave cambia (p. ej. IndexedDB borrada), la cookie vieja no sirve."""
    admin.key = DpopKey()
    assert (await admin.get(ME)).status_code == 401


async def test_respuesta_trae_request_id(admin):
    response = await admin.get(ME, headers={"X-Request-ID": "req-123"})
    assert response.headers["x-request-id"] == "req-123"
