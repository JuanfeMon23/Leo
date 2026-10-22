"""Autogestion del propio usuario (barra superior de las apps): ver y editar
el perfil, y cambiar la contrasena. Solo exige sesion SSO (cookie + DPoP):
NINGUN permiso `leo.*`. No hay id en la ruta: nadie edita a otro."""

import json

from sqlalchemy import select

from app.conftest import login_as
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import Session, Token, TokenType
from app.modules.users.models import User
from app.testkit import (
    COOKIE,
    STRONG_PASSWORD,
    make_client_app,
    make_user,
)

ME = "/api/v1/auth/me"
PROFILE = "/api/v1/auth/me/profile"
PASSWORD = "/api/v1/auth/me/password"
NEW_PASSWORD = "Otra-Clave-Nueva-2027#"


async def events(session, tag: str, **filters) -> list[AuditEvent]:
    stmt = select(AuditEvent).where(AuditEvent.action_tag == tag)
    for name, value in filters.items():
        stmt = stmt.where(getattr(AuditEvent, name) == value)
    return list(await session.scalars(stmt.execution_options(populate_existing=True)))


async def user_nav(session, make_browser, **overrides):
    """Persona SIN ningun rol (ni un permiso `leo.*`) con sesion SSO."""
    user = await make_user(session, **overrides)
    return await login_as(session, make_browser, user)


async def reload(session, user: User) -> User:
    return (
        await session.scalars(
            select(User)
            .where(User.id == user.id)
            .execution_options(populate_existing=True)
        )
    ).one()


# --- GET /auth/me ---


async def test_me_incluye_lo_que_necesita_la_barra(session, make_browser):
    nav = await user_nav(session, make_browser, first_name="Ana", last_name="Gómez")

    response = await nav.get(ME)

    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert user == {
        "id": str(nav.user.id),
        "username": nav.user.username,
        "name": "Ana Gómez",
        "first_name": "Ana",
        "last_name": "Gómez",
        "email": nav.user.email,
    }
    assert "document_number" not in user and "password_hash" not in user


# --- PATCH /auth/me/profile ---


async def test_edita_nombres_y_correo_sin_permisos_leo(session, make_browser):
    nav = await user_nav(session, make_browser)

    response = await nav.patch(
        PROFILE,
        json={
            "first_name": "  Beatriz ",
            "last_name": "Pérez",
            "email": "Nuevo.Correo@Example.com",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["first_name"] == "Beatriz"
    assert body["user"]["last_name"] == "Pérez"
    assert body["user"]["name"] == "Beatriz Pérez"
    assert body["user"]["email"] == "Nuevo.Correo@Example.com"
    assert set(body) == {"user", "session", "permissions", "applications"}
    stored = await reload(session, nav.user)
    assert (stored.first_name, stored.email) == ("Beatriz", "Nuevo.Correo@Example.com")
    assert (await nav.get(ME)).json()["user"]["first_name"] == "Beatriz"


async def test_edicion_parcial_solo_cambia_lo_enviado(session, make_browser):
    nav = await user_nav(session, make_browser, first_name="Ana", last_name="Gómez")

    response = await nav.patch(PROFILE, json={"last_name": "Ruiz"})

    assert response.status_code == 200, response.text
    assert response.json()["user"]["first_name"] == "Ana"
    assert response.json()["user"]["last_name"] == "Ruiz"


async def test_edicion_audita_diff_sin_datos_sensibles(session, make_browser):
    nav = await user_nav(session, make_browser, first_name="Ana")

    await nav.patch(PROFILE, json={"first_name": "Beatriz"})

    [event] = await events(session, "leo.users.edit", entity_id=str(nav.user.id))
    assert event.entity_type == "user"
    assert event.actor_user_id == nav.user.id
    assert event.reason == "autogestión"
    assert event.result == "ok"
    assert event.changes == {"first_name": {"before": "Ana", "after": "Beatriz"}}
    dumped = json.dumps(event.changes)
    for secret in ("password", "hash", "argon2", "document", STRONG_PASSWORD):
        assert secret not in dumped


async def test_sin_cambios_reales_no_escribe_ni_audita(session, make_browser):
    nav = await user_nav(session, make_browser, first_name="Ana")
    before = (await reload(session, nav.user)).updated_at

    same = await nav.patch(PROFILE, json={"first_name": "Ana", "email": nav.user.email})
    empty = await nav.patch(PROFILE, json={})

    assert same.status_code == 200 and empty.status_code == 200
    assert (await reload(session, nav.user)).updated_at == before
    assert await events(session, "leo.users.edit", entity_id=str(nav.user.id)) == []


async def test_campos_no_editables_se_rechazan(session, make_browser):
    """Ataque: autogestion no permite cambiar usuario, documento, estado ni
    credenciales (escalada / suplantacion de identidad)."""
    nav = await user_nav(session, make_browser)
    original = await reload(session, nav.user)
    for field, value in [
        ("username", "otro-usuario"),
        ("document_type", "CE"),
        ("document_number", "999"),
        ("is_active", False),
        ("password", NEW_PASSWORD),
        ("password_hash", "x"),
        ("roles", []),
        ("role_ids", []),
        ("failed_login_attempts", 0),
    ]:
        response = await nav.patch(PROFILE, json={"first_name": "Zed", field: value})
        assert response.status_code == 422, (field, response.text)
        body = response.json()
        assert body["code"] == "validation_error"
        assert body["details"][0]["field"] == field
        assert body["details"][0]["message"]  # legible
    stored = await reload(session, nav.user)
    assert stored.first_name == original.first_name  # nada se aplico a medias
    assert (stored.username, stored.document_number, stored.is_active) == (
        original.username,
        original.document_number,
        True,
    )


async def test_valida_longitudes_trim_y_formato_de_correo(session, make_browser):
    nav = await user_nav(session, make_browser)
    for payload in [
        {"first_name": "   "},
        {"first_name": "x" * 101},
        {"last_name": ""},
        {"first_name": None},
        {"email": "sin-arroba"},
        {"email": "dos@@arrobas.com"},
        {"email": "con espacio@x.com"},
        {"email": "a@b.com" + "x" * 250},
        {"email": None},
    ]:
        response = await nav.patch(PROFILE, json=payload)
        assert response.status_code == 422, (payload, response.text)
        assert response.json()["code"] == "validation_error"


async def test_correo_duplicado_sin_distinguir_mayusculas(session, make_browser):
    other = await make_user(session, email="ocupado@example.com")
    nav = await user_nav(session, make_browser)

    for email in ("ocupado@example.com", "OCUPADO@Example.COM"):
        response = await nav.patch(PROFILE, json={"email": email})
        assert response.status_code == 409, response.text
        body = response.json()
        assert body["code"] == "duplicate"
        assert body["details"] == {"email": email}
        assert "email" in body["message"]
    assert (await reload(session, nav.user)).email == nav.user.email
    assert (await reload(session, other)).email == "ocupado@example.com"


async def test_puede_cambiar_solo_mayusculas_de_su_propio_correo(session, make_browser):
    nav = await user_nav(session, make_browser, email="ana@example.com")

    response = await nav.patch(PROFILE, json={"email": "Ana@Example.com"})

    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "Ana@Example.com"


async def test_perfil_sin_sesion_401(browser):
    response = await browser.patch(PROFILE, json={"first_name": "X"})
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


async def test_perfil_con_cookie_robada_401(session, make_browser):
    nav = await user_nav(session, make_browser)
    thief = make_browser()
    thief.client.cookies.set(COOKIE, nav.client.cookies.get(COOKIE), domain="leo.test")

    response = await thief.patch(PROFILE, json={"first_name": "Robado"})

    assert response.status_code == 401
    assert (await reload(session, nav.user)).first_name != "Robado"


async def test_no_se_puede_editar_a_otro_usuario(session, make_browser):
    """No hay id en la ruta ni en el cuerpo: siempre se edita el de la sesion."""
    victim = await make_user(session, first_name="Victima")
    nav = await user_nav(session, make_browser)

    by_body = await nav.patch(PROFILE, json={"id": str(victim.id), "first_name": "X"})
    by_path = await nav.patch(f"{PROFILE}/{victim.id}", json={"first_name": "X"})
    own = await nav.patch(PROFILE, json={"first_name": "Mio"})

    assert by_body.status_code == 422
    assert by_path.status_code in (404, 405)
    assert own.status_code == 200
    assert (await reload(session, victim)).first_name == "Victima"
    assert (await reload(session, nav.user)).first_name == "Mio"


async def test_token_de_servicio_no_accede(session, client):
    app = await make_client_app(session)
    await session.commit()

    for method, path, body in [
        ("PATCH", PROFILE, {"first_name": "X"}),
        ("POST", PASSWORD, {"current_password": "a", "new_password": "b"}),
    ]:
        response = await client.request(
            method,
            path,
            json=body,
            headers={"Authorization": "Bearer abc", **app.basic()},
        )
        assert response.status_code == 401, response.text


# --- POST /auth/me/password ---


def passwords(current: str = STRONG_PASSWORD, new: str = NEW_PASSWORD) -> dict:
    return {"current_password": current, "new_password": new}


async def test_cambia_la_contrasena_y_la_antigua_deja_de_servir(session, make_browser):
    nav = await user_nav(session, make_browser)

    response = await nav.post(PASSWORD, json=passwords())

    assert response.status_code == 204, response.text
    assert response.content == b""
    stored = await reload(session, nav.user)
    assert stored.password_hash.startswith("$argon2id$")
    assert NEW_PASSWORD not in stored.password_hash
    fresh = make_browser()
    assert (await fresh.login(nav.user.username, STRONG_PASSWORD)).status_code == 401
    assert (await fresh.login(nav.user.username, NEW_PASSWORD)).status_code == 200


async def test_revoca_las_otras_sesiones_y_mantiene_la_actual(session, make_browser):
    user = await make_user(session)
    current = await login_as(session, make_browser, user)
    other = await login_as(session, make_browser, user)
    sessions_before = list(
        await session.scalars(select(Session).where(Session.user_id == user.id))
    )
    assert len(sessions_before) == 2

    response = await current.post(PASSWORD, json=passwords())

    assert response.status_code == 204, response.text
    assert (await current.get(ME)).status_code == 200  # la actual sigue
    assert (await other.get(ME)).status_code == 401  # la otra, revocada
    rows = list(
        await session.scalars(
            select(Session)
            .where(Session.user_id == user.id)
            .execution_options(populate_existing=True)
        )
    )
    revoked = [s for s in rows if s.revoked_at is not None]
    alive = [s for s in rows if s.revoked_at is None]
    assert len(revoked) == 1 and len(alive) == 1
    assert revoked[0].revoked_reason == "password-change"


async def test_revoca_tokens_de_apps_de_las_otras_sesiones(session, make_browser):
    user = await make_user(session)
    current = await login_as(session, make_browser, user)
    other = await login_as(session, make_browser, user)
    app = await make_client_app(session)
    sessions = list(
        await session.scalars(select(Session).where(Session.user_id == user.id))
    )
    victim_session = next(s for s in sessions if s.jkt == other.key.jkt)
    session.add(
        Token(
            token_hash="a" * 64,
            token_type=TokenType.ACCESS,
            session_id=victim_session.id,
            application_id=app.app.id,
            jkt=other.key.jkt,
            expires_at=victim_session.expires_at,
        )
    )
    await session.flush()

    assert (await current.post(PASSWORD, json=passwords())).status_code == 204

    token = (
        await session.scalars(
            select(Token)
            .where(Token.token_hash == "a" * 64)
            .execution_options(populate_existing=True)
        )
    ).one()
    assert token.revoked_at is not None


async def test_contrasena_actual_incorrecta_401_generico_y_cuenta_intentos(
    session, make_browser
):
    nav = await user_nav(session, make_browser)

    response = await nav.post(PASSWORD, json=passwords(current="Incorrecta-123!"))

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "invalid_credentials"
    assert "Incorrecta" not in response.text and NEW_PASSWORD not in response.text
    stored = await reload(session, nav.user)
    assert NEW_PASSWORD not in stored.password_hash
    assert (await nav.get(ME)).status_code == 200  # la sesion sigue viva
    [event] = await events(session, "leo.users.reset-password", result="denied")
    assert event.actor_user_id == nav.user.id
    assert (event.reason or "").startswith("autogestión")
    assert "Incorrecta" not in json.dumps(event.changes) + (event.reason or "")
    assert (await make_browser().login(nav.user.username)).status_code == 200


async def test_intentos_fallidos_repetidos_dan_429(session, make_browser):
    nav = await user_nav(session, make_browser)
    bad = passwords(current="Incorrecta-123!")

    for _ in range(5):  # LEO_LOGIN_MAX_FAILED_ATTEMPTS en los tests
        assert (await nav.post(PASSWORD, json=bad)).status_code == 401
    blocked = await nav.post(PASSWORD, json=passwords())  # hasta la correcta

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_attempts"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert NEW_PASSWORD not in (await reload(session, nav.user)).password_hash


async def test_rate_limit_por_ip_con_distintos_usuarios(session, make_browser):
    navs = [await user_nav(session, make_browser) for _ in range(3)]
    bad = passwords(current="Incorrecta-123!")
    codes = []
    for index in range(30):
        codes.append((await navs[index % 3].post(PASSWORD, json=bad)).status_code)
    assert 429 in codes  # LEO_LOGIN_RATE_LIMIT_PER_MINUTE = 20 por IP


async def test_contrasena_debil_422(session, make_browser):
    nav = await user_nav(
        session, make_browser, username="marta.lopez", email="marta.lopez@example.com"
    )
    for weak in [
        "corta1A!",
        "sinmayusculas-123!",
        "SINMINUSCULAS-123!",
        "SinNumeros-Aqui!!",
        "SinSimbolo12345",
        "A1!" + "a" * 130,  # demasiado larga
    ]:
        response = await nav.post(PASSWORD, json=passwords(new=weak))
        assert response.status_code == 422, (weak, response.text)
        body = response.json()
        assert body["code"] in ("weak_password", "validation_error")
        assert body["message"]
    weak = (await nav.post(PASSWORD, json=passwords(new="corta"))).json()
    assert weak["code"] == "weak_password"
    assert weak["details"]["password"]  # requisitos incumplidos, legibles
    assert (await reload(session, nav.user)).password_hash  # sin cambios
    assert (await make_browser().login(nav.user.username)).status_code == 200


async def test_contrasena_con_usuario_o_parte_local_del_correo_se_acepta(
    session, make_browser
):
    nav = await user_nav(
        session, make_browser, username="marta.lopez", email="marta.lopez@example.com"
    )

    response = await nav.post(PASSWORD, json=passwords(new="Xmarta.lopezX-1234"))

    assert response.status_code in (200, 204), response.text


async def test_nueva_igual_a_la_actual_422(session, make_browser):
    nav = await user_nav(session, make_browser)

    response = await nav.post(PASSWORD, json=passwords(new=STRONG_PASSWORD))

    assert response.status_code == 422
    assert response.json()["code"] == "same_password"


async def test_cambio_correcto_reinicia_intentos_y_bloqueo(session, make_browser):
    nav = await user_nav(session, make_browser)
    user = await reload(session, nav.user)
    user.failed_login_attempts = 3
    await session.flush()

    assert (await nav.post(PASSWORD, json=passwords())).status_code == 204

    stored = await reload(session, nav.user)
    assert stored.failed_login_attempts == 0 and stored.locked_until is None


async def test_cambio_audita_sin_secretos(session, make_browser, caplog):
    nav = await user_nav(session, make_browser)
    caplog.set_level("DEBUG")

    response = await nav.post(PASSWORD, json=passwords())

    assert response.status_code == 204
    [event] = await events(
        session, "leo.users.reset-password", entity_id=str(nav.user.id)
    )
    assert event.result == "ok" and event.reason == "autogestión"
    assert event.entity_type == "user" and event.actor_user_id == nav.user.id
    stored = await reload(session, nav.user)
    blob = json.dumps(event.changes) + (event.reason or "") + response.text
    for secret in (STRONG_PASSWORD, NEW_PASSWORD, stored.password_hash, "argon2"):
        assert secret not in blob
        assert secret not in caplog.text


async def test_contrasena_sin_sesion_401(browser):
    response = await browser.post(PASSWORD, json=passwords())
    assert response.status_code == 401


async def test_contrasena_rechaza_campos_extra_y_faltantes(session, make_browser):
    nav = await user_nav(session, make_browser)
    for payload in [
        {"current_password": STRONG_PASSWORD},
        {"new_password": NEW_PASSWORD},
        {**passwords(), "user_id": str(nav.user.id)},
        {"current_password": "", "new_password": NEW_PASSWORD},
    ]:
        response = await nav.post(PASSWORD, json=payload)
        assert response.status_code == 422, (payload, response.text)
