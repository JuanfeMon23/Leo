"""API `/api/v1/settings`: permisos (view / edit / edit-security), errores,
bloqueo optimista, historial y auditoria central."""

import pytest
from sqlalchemy import select

from app.conftest import login_as
from app.modules.audit.models import AuditEvent
from app.testkit import grant, leo_app, make_role, make_user

SETTINGS = "/api/v1/settings"
IDLE = f"{SETTINGS}/auth.idle_timeout_minutes"
LOCK_ATTEMPTS = f"{SETTINGS}/auth.login_max_failed_attempts"


async def nav_with(session, make_browser, *tags: str):
    role = await make_role(session, (await leo_app(session)).id, list(tags))
    user = await make_user(session)
    await grant(session, user, role)
    return await login_as(session, make_browser, user)


def body(value, version=1, reason="Cambio de política"):
    return {"value": value, "reason": reason, "expected_version": version}


async def update_events(session):
    stmt = select(AuditEvent).where(AuditEvent.action_tag == "leo.settings.update")
    return list(await session.scalars(stmt))


async def test_listado_agrupado_con_el_contrato_completo(admin):
    response = await admin.get(SETTINGS)
    assert response.status_code == 200, response.text
    groups = {g["group"]: g["settings"] for g in response.json()["groups"]}
    assert set(groups) == {"audit", "auth", "pagination", "password", "rate_limit"}
    idle = next(s for s in groups["auth"] if s["key"] == "auth.idle_timeout_minutes")
    assert idle == {
        **idle,
        "type": "int",
        "default": 30,
        "min": 5,
        "max": 120,
        "unit": "minutes",
        "version": 1,
        "requires_security_permission": False,
        "updated_by": None,
    }
    assert idle["description"]
    lock = next(
        s for s in groups["auth"] if s["key"] == "auth.login_max_failed_attempts"
    )
    assert lock["requires_security_permission"] is True


async def test_ver_exige_permiso_view(session, make_browser):
    nav = await nav_with(session, make_browser, "leo.settings.edit")
    assert (await nav.get(SETTINGS)).status_code == 403
    assert (await nav.get(f"{IDLE}/history")).status_code == 403


async def test_solo_view_no_puede_editar(session, make_browser):
    nav = await nav_with(session, make_browser, "leo.settings.view")
    assert (await nav.get(SETTINGS)).status_code == 200
    assert (await nav.put(IDLE, json=body(45))).status_code == 403


async def test_edit_cambia_valor_audita_y_deja_historial(session, make_browser):
    nav = await nav_with(
        session, make_browser, "leo.settings.view", "leo.settings.edit"
    )
    response = await nav.put(IDLE, json=body(45))
    assert response.status_code == 200, response.text
    out = response.json()
    assert (out["value"], out["version"], out["updated_by_username"]) == (
        45,
        2,
        nav.user.username,
    )
    (event,) = await update_events(session)
    assert event.entity_id == "auth.idle_timeout_minutes"
    assert event.changes == {"value": {"before": 30, "after": 45}}
    assert event.reason == "Cambio de política"
    assert event.actor_user_id == nav.user.id
    history = (await nav.get(f"{IDLE}/history")).json()
    assert history["total"] == 1
    assert history["items"][0]["old_value"] == 30
    assert history["items"][0]["changed_by_username"] == nav.user.username
    listed = (await nav.get(SETTINGS)).json()["groups"]
    auth = next(g for g in listed if g["group"] == "auth")["settings"]
    idle = next(s for s in auth if s["key"] == "auth.idle_timeout_minutes")
    assert idle["value"] == 45


async def test_clave_de_seguridad_exige_edit_security(session, make_browser):
    plain = await nav_with(
        session, make_browser, "leo.settings.view", "leo.settings.edit"
    )
    assert (await plain.put(LOCK_ATTEMPTS, json=body(6))).status_code == 403
    assert await update_events(session) == []
    secure = await nav_with(
        session,
        make_browser,
        "leo.settings.view",
        "leo.settings.edit",
        "leo.settings.edit-security",
    )
    assert (await secure.put(LOCK_ATTEMPTS, json=body(6))).status_code == 200


async def test_admin_tiene_los_tres_permisos(admin):
    assert (await admin.put(LOCK_ATTEMPTS, json=body(7))).status_code == 200


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        (body(500), 422, "setting_out_of_range"),
        (body("45"), 422, "setting_type_mismatch"),
        (body(45.5), 422, "setting_type_mismatch"),
        (body(45, reason="ab"), 422, "reason_required"),
        (body(45, reason=""), 422, "reason_required"),
        (body(45, version=9), 409, "version_conflict"),
    ],
)
async def test_errores_legibles(admin, session, payload, status, code):
    response = await admin.put(IDLE, json=payload)
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert response.json()["message"]
    assert await update_events(session) == []


async def test_fuera_de_rango_informa_min_y_max(admin):
    response = await admin.put(IDLE, json=body(500))
    assert response.json()["details"]["min"] == 5
    assert response.json()["details"]["max"] == 120
    assert "entre 5 y 120" in response.json()["message"]


async def test_clave_inexistente_404(admin):
    assert (await admin.put(f"{SETTINGS}/no.existe", json=body(1))).status_code == 404
    assert (await admin.get(f"{SETTINGS}/no.existe/history")).status_code == 404


async def test_conflicto_de_version_entre_dos_editores(admin):
    assert (await admin.put(IDLE, json=body(40))).status_code == 200
    stale = await admin.put(IDLE, json=body(50, version=1))
    assert stale.status_code == 409
    assert stale.json()["details"]["current_version"] == 2
    assert (await admin.put(IDLE, json=body(50, version=2))).status_code == 200
