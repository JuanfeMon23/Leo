"""Login SSO: cookie HttpOnly atada al jkt, mensajes genericos, bloqueo por
intentos y rate limit, auditoria de cada resultado."""

from sqlalchemy import select, text

from app.core.crypto import sha256_hex
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import Session
from app.modules.users.models import User
from app.testkit import COOKIE, STRONG_PASSWORD, grant, leo_admin_role, make_user

LOGIN = "/api/v1/auth/login"


async def events(session, tag: str, **filters) -> list[AuditEvent]:
    stmt = select(AuditEvent).where(AuditEvent.action_tag == tag)
    for name, value in filters.items():
        stmt = stmt.where(getattr(AuditEvent, name) == value)
    return list(await session.scalars(stmt))


async def test_login_correcto_crea_sesion_atada_al_jkt_y_cookie_segura(
    session, browser
):
    user = await make_user(session)
    await session.commit()

    response = await browser.login(user.username)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["username"] == user.username
    assert set(body) == {"user", "session", "permissions", "applications"}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=")
    for attr in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert attr.lower() in cookie.lower()
    sso = (
        await session.scalars(select(Session).where(Session.user_id == user.id))
    ).one()
    assert sso.jkt == browser.key.jkt
    assert str(sso.ip) == "127.0.0.1"
    # La cookie es un secreto opaco de 256 bits; en BD solo su SHA-256, en la
    # sesion (no es un token de la tabla `tokens`).
    secret = browser.client.cookies.get(COOKIE)
    assert secret and len(secret) >= 43
    assert sso.secret_hash == sha256_hex(secret) != secret
    cookie_tokens = await session.scalar(
        text(
            "SELECT count(*) FROM tokens WHERE session_id = :s "
            "OR token_hash IN (:v, :h)"
        ),
        {"s": sso.id, "v": secret, "h": sha256_hex(secret)},
    )
    assert cookie_tokens == 0
    await session.refresh(user)
    assert user.last_login_at is not None
    assert (
        len(await events(session, "leo.auth.login", actor_user_id=user.id, result="ok"))
        == 1
    )


async def test_login_por_email_sin_distinguir_mayusculas(session, browser):
    user = await make_user(session)
    await session.commit()
    response = await browser.login(user.email.upper())
    assert response.status_code == 200, response.text


async def test_login_sin_dpop_se_rechaza(session, browser):
    user = await make_user(session)
    await session.commit()
    response = await browser.post(
        LOGIN, json={"login": user.username, "password": STRONG_PASSWORD}, dpop=False
    )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_dpop_proof"
    assert response.headers["www-authenticate"].startswith("DPoP")


async def test_contrasena_incorrecta_y_usuario_inexistente_dan_el_mismo_error(
    session, browser
):
    user = await make_user(session)
    await session.commit()

    wrong = await browser.login(user.username, "Otra-Clave-Mala-1!")
    missing = await browser.login("no-existe-nadie", "Otra-Clave-Mala-1!")

    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()
    assert wrong.json()["message"] == "Usuario o contraseña incorrectos."
    denied = await events(session, "leo.auth.login", result="denied")
    assert len(denied) == 2


async def test_bloqueo_tras_n_fallos_y_luego_429_aun_con_la_clave_correcta(
    session, browser
):
    user = await make_user(session)
    await session.commit()

    statuses = [
        (await browser.login(user.username, "Clave-Incorrecta-9!")).status_code
        for _ in range(5)
    ]
    assert statuses == [401, 401, 401, 401, 429]
    blocked = await browser.login(user.username)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_attempts"
    assert int(blocked.headers["retry-after"]) > 0
    await session.refresh(user)
    assert user.locked_until is not None
    assert len(await events(session, "leo.auth.lock", actor_user_id=user.id)) == 1


async def test_usuario_inexistente_se_bloquea_igual_que_uno_existente(session, browser):
    statuses = [
        (await browser.login("fantasma-inexistente", "Clave-Incorrecta-9!")).status_code
        for _ in range(6)
    ]
    assert statuses == [401, 401, 401, 401, 401, 429]


async def test_desbloqueo_por_tiempo(session, browser, monkeypatch):
    from datetime import timedelta

    from app.core import clock

    user = await make_user(session)
    await session.commit()
    for _ in range(5):
        await browser.login(user.username, "Clave-Incorrecta-9!")
    later = clock.now() + timedelta(minutes=16)
    monkeypatch.setattr(clock, "now", lambda: later)
    assert (await browser.login(user.username)).status_code == 200


async def test_rate_limit_por_ip(session, browser):
    statuses = {
        (await browser.login(f"user-{i}", "Clave-Incorrecta-9!")).status_code
        for i in range(21)
    }
    assert 429 in statuses


async def test_usuario_desactivado_con_clave_correcta_recibe_403(session, browser):
    user = await make_user(session, is_active=False)
    await session.commit()
    response = await browser.login(user.username)
    assert response.status_code == 403
    assert response.json()["code"] == "user_inactive"


async def test_usuario_desactivado_con_clave_incorrecta_recibe_el_mensaje_generico(
    session, browser
):
    user = await make_user(session, is_active=False)
    await session.commit()
    response = await browser.login(user.username, "Clave-Incorrecta-9!")
    assert response.status_code == 401


async def test_me_devuelve_permisos_leo_y_apps_accesibles(session, admin):
    response = await admin.get("/api/v1/auth/me")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "leo.users.create" in body["permissions"]
    assert body["permissions"] == sorted(body["permissions"])
    assert [a["slug"] for a in body["applications"]] == ["leo"]
    assert body["session"]["idle_timeout_seconds"] == 1800


async def test_login_exitoso_reinicia_el_contador_de_fallos(session, browser):
    user = await make_user(session)
    await session.commit()
    await browser.login(user.username, "Clave-Incorrecta-9!")
    assert (await browser.login(user.username)).status_code == 200
    refreshed = await session.get(User, user.id, populate_existing=True)
    assert refreshed.failed_login_attempts == 0


async def test_permisos_leo_solo_de_roles_activos(session, make_browser):
    from app.conftest import login_as

    user = await make_user(session)
    role = await leo_admin_role(session)
    await grant(session, user, role)
    nav = await login_as(session, make_browser, user)
    role.is_active = False
    await session.commit()
    body = (await nav.get("/api/v1/auth/me")).json()
    assert body["permissions"] == []
    assert body["applications"] == []
