"""Los consumidores leen `settings` en cada peticion: cambiar un ajuste en la
BD cambia el comportamiento SIN reiniciar."""

from dataclasses import replace
from datetime import timedelta

from sqlalchemy import select, text

from app.core import clock, runtime_settings
from app.modules.auth.models import Session
from app.modules.users.tests.test_users import USERS, new_user
from app.testkit import make_user, set_setting

BAD = "Clave-Incorrecta-9!"


async def test_login_max_failed_attempts_se_aplica_sin_reiniciar(session, browser):
    await set_setting(session, "auth.login_max_failed_attempts", 3)
    user = await make_user(session)
    await session.commit()
    statuses = [(await browser.login(user.username, BAD)).status_code for _ in range(3)]
    assert statuses == [401, 401, 429]


async def test_login_lock_minutes_se_aplica_sin_reiniciar(
    session, browser, monkeypatch
):
    await set_setting(session, "auth.login_lock_minutes", 2)
    user = await make_user(session)
    await session.commit()
    for _ in range(5):
        await browser.login(user.username, BAD)
    later = clock.now() + timedelta(minutes=3)
    monkeypatch.setattr(clock, "now", lambda: later)
    assert (await browser.login(user.username)).status_code == 200


async def test_bloqueo_de_login_inexistente_usa_los_mismos_ajustes(session, browser):
    await set_setting(session, "auth.login_max_failed_attempts", 3)
    statuses = [(await browser.login("fantasma", BAD)).status_code for _ in range(4)]
    assert statuses == [401, 401, 401, 429]


async def test_rate_limit_de_login_por_ip_cambia_sin_reiniciar(session, browser):
    await set_setting(session, "rate_limit.login_ip_per_window", 3)
    statuses = [(await browser.login(f"user-{i}", BAD)).status_code for i in range(4)]
    assert statuses == [401, 401, 401, 429]


async def test_ventana_del_rate_limit_es_un_ajuste(session, browser, monkeypatch):
    await set_setting(session, "rate_limit.login_ip_per_window", 3)
    await set_setting(session, "rate_limit.window_seconds", 10)
    for i in range(3):
        await browser.login(f"user-{i}", BAD)
    assert (await browser.login("user-x", BAD)).status_code == 429
    later = clock.now() + timedelta(seconds=11)
    monkeypatch.setattr(clock, "now", lambda: later)
    assert (await browser.login("user-y", BAD)).status_code == 401


async def test_vida_maxima_de_sesion_es_un_ajuste(session, browser):
    await set_setting(session, "auth.session_max_hours", 3)
    user = await make_user(session)
    await session.commit()
    assert (await browser.login(user.username)).status_code == 200
    sso = (
        await session.scalars(select(Session).where(Session.user_id == user.id))
    ).one()
    assert abs((sso.expires_at - sso.created_at).total_seconds() - 3 * 3600) < 60


async def test_contrasena_sube_el_minimo_pero_no_baja_del_piso(admin, session):
    assert (
        await admin.post(USERS, json=new_user(password="Clave-Segura-1!"))
    ).status_code == 201
    await set_setting(session, "password.min_length", 16)
    response = await admin.post(
        USERS,
        json=new_user("otra", password="Clave-Segura-1!", document_number="777"),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "weak_password"
    assert "entre 16 y 128" in response.json()["details"]["password"][0]
    # El piso de 12 es de codigo: ni un valor corrupto en la BD lo baja (el
    # store lo descarta por estar fuera del rango del registro).
    await session.execute(
        text(
            "UPDATE settings SET min_value = '1', value = '4' "
            "WHERE key = 'password.min_length'"
        )
    )
    runtime_settings.store.invalidate()
    response = await admin.post(
        USERS,
        json=new_user("tercera", password="Ab-1xyz-9", document_number="888"),
    )
    assert response.status_code == 422
    assert "entre 12 y 128" in response.json()["details"]["password"][0]


async def test_clases_de_caracteres_de_la_contrasena_son_ajustes(admin, session):
    no_symbol = new_user("sinsimbolo", password="ClaveSegura2026ab")
    assert (await admin.post(USERS, json=no_symbol)).status_code == 422
    await set_setting(session, "password.require_symbol", False)
    assert (await admin.post(USERS, json=no_symbol)).status_code == 201


async def test_maximo_de_page_size_es_un_ajuste(admin, session):
    assert (await admin.get(f"{USERS}?page_size=200")).status_code == 200
    await set_setting(session, "pagination.max_page_size", 50)
    assert (await admin.get(f"{USERS}?page_size=50")).status_code == 200
    too_big = await admin.get(f"{USERS}?page_size=51")
    assert too_big.status_code == 422
    assert too_big.json()["code"] == "validation_error"
    assert "50" in too_big.json()["message"]


async def test_maximo_de_filas_del_export_es_un_ajuste(admin, session, monkeypatch):
    # Con el minimo real (1000) no habria como probar el corte: se baja solo
    # en el registro del test.
    definition = runtime_settings.LEO_SETTINGS.get("audit.export_max_rows")
    monkeypatch.setitem(
        runtime_settings.LEO_SETTINGS._defs,
        definition.key,
        replace(definition, min=1),
    )
    for version, value in ((1, 40), (2, 41)):  # cada edicion genera un evento
        edit = {"value": value, "reason": "prueba", "expected_version": version}
        await admin.put("/api/v1/settings/auth.idle_timeout_minutes", json=edit)
    await session.execute(
        text(
            "UPDATE settings SET min_value = '1', value = '2' "
            "WHERE key = 'audit.export_max_rows'"
        )
    )
    runtime_settings.store.invalidate()
    response = await admin.get("/api/v1/audit/events/export")
    rows = response.content.decode("utf-8-sig").strip().splitlines()
    assert len(rows) == 1 + 2


async def test_sin_bd_los_consumidores_usan_el_default_del_registro(monkeypatch):
    def broken():
        raise ConnectionError("BD caída")

    monkeypatch.setattr(runtime_settings.store, "session_factory", broken)
    runtime_settings.store.invalidate()
    assert await runtime_settings.get("auth.idle_timeout_minutes") == 30
    assert (await runtime_settings.password_policy()).min_length == 12
    runtime_settings.store.invalidate()
