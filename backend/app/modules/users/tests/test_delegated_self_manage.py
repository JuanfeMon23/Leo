"""Autogestion delegada: `PATCH /users/service/delegated/profile` y
`POST /users/service/delegated/password`. Una app (BFF) con el rol
`leo-self-service-delegate` actua con el access token del usuario emitido a
ELLA; Leo deriva el usuario del token (nunca de un id del cliente)."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from app.conftest import login_as
from app.core import clock
from app.core.db.seeds.catalog import (
    LEO_DELEGATE_ROLE_SLUG,
    LEO_SERVICE_GRANTABLE_ROLE_SLUGS,
)
from app.core.db.seeds.leo_app import seed_leo_delegate_role
from app.core.tests.dpop_keys import DpopKey
from app.modules.applications.models import Action
from app.modules.audit.models import AuditEvent
from app.modules.auth import login_limiters
from app.modules.auth.models import Session, SessionRevokedReason
from app.modules.roles.models import Role, RoleAction
from app.modules.users.models import User
from app.testkit import (
    STRONG_PASSWORD,
    grant,
    grant_service_access,
    leo_admin_role,
    leo_app,
    make_client_app,
    make_role,
    make_user,
    pkce_pair,
    set_setting,
)

PROFILE = "/api/v1/users/service/delegated/profile"
PASSWORD = "/api/v1/users/service/delegated/password"
TOKEN = "/api/v1/auth/token"
AUTHORIZE = "/api/v1/auth/authorize"
TAG = "leo.users.delegated-self-manage"
NEW_PASSWORD = "Otra-Clave-Nueva-2027#"
WRONG = "Clave-Incorrecta-1!"


async def events(session, tag, **filters):
    stmt = select(AuditEvent).where(AuditEvent.action_tag == tag)
    for name, value in filters.items():
        stmt = stmt.where(getattr(AuditEvent, name) == value)
    return list(await session.scalars(stmt.execution_options(populate_existing=True)))


async def reload(session, user):
    return (
        await session.scalars(
            select(User).where(User.id == user.id).execution_options(populate_existing=True)
        )
    ).one()


class World:
    """App `acu` con el rol delegado concedido, y un paciente con rol en ella."""

    def __init__(self, session, make_browser, client):
        self.session, self.make_browser, self.client = session, make_browser, client

    async def service_headers(self, creds=None) -> dict[str, str]:
        response = await self.client.post(
            TOKEN,
            json={"grant_type": "client_credentials", "audience": "leo"},
            headers=(creds or self.caller).basic(),
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    async def user_token(self, user, app=None, role=None) -> tuple[str, "object"]:
        """Login del usuario en Leo + authorize + canje por la app. Devuelve
        (access_token, navegador); un navegador por llamada = una sesion SSO."""
        app = app or self.caller
        nav = await login_as(self.session, self.make_browser, user)
        verifier, challenge = pkce_pair()
        device = DpopKey()
        authorize = await nav.post(
            AUTHORIZE,
            json={
                "client_id": app.client_id,
                "redirect_uri": app.app.redirect_uris[0],
                "state": "s",
                "code_challenge": challenge,
                "dpop_jkt": device.jkt,
            },
        )
        assert authorize.status_code == 200, authorize.text
        code = parse_qs(urlsplit(authorize.json()["redirect_to"]).query)["code"][0]
        exchange = await self.client.post(
            TOKEN,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": app.app.redirect_uris[0],
                "jkt": device.jkt,
            },
            headers=app.basic(),
        )
        assert exchange.status_code == 200, exchange.text
        return exchange.json()["access_token"], nav

    async def patient(self, **overrides) -> User:
        user = await make_user(self.session, **overrides)
        await grant(self.session, user, self.app_role)
        return user

    async def profile(self, token, headers=None, **fields):
        headers = headers if headers is not None else await self.service_headers()
        return await self.client.patch(
            PROFILE, json={"user_access_token": token, **fields}, headers=headers
        )

    async def password(self, token, current=STRONG_PASSWORD, new=NEW_PASSWORD, headers=None):
        headers = headers if headers is not None else await self.service_headers()
        return await self.client.post(
            PASSWORD,
            json={"user_access_token": token, "current_password": current, "new_password": new},
            headers=headers,
        )


@pytest.fixture(autouse=True)
async def _reset():
    """Los limitadores son de proceso: cada test empieza limpio."""
    await login_limiters().reset()


@pytest.fixture
async def world(session, make_browser, client):
    leo = await leo_app(session)
    conn = await session.connection()
    await conn.run_sync(lambda sync: seed_leo_delegate_role(sync, leo.id))
    w = World(session, make_browser, client)
    w.caller = await make_client_app(session, slug="acu", tags=["items.view"])
    w.app_role = await make_role(session, w.caller.app.id, ["acu.items.view"])
    w.delegate = (
        await session.scalars(
            select(Role).where(Role.application_id == leo.id, Role.slug == LEO_DELEGATE_ROLE_SLUG)
        )
    ).one()
    await grant_service_access(session, w.caller.app, w.delegate)
    await session.commit()
    return w


# --- semilla y concesion ---


async def test_rol_delegado_solo_tiene_la_accion_y_semilla_idempotente(world):
    conn = await world.session.connection()
    await conn.run_sync(lambda sync: seed_leo_delegate_role(sync, world.delegate.application_id))
    roles = (
        await world.session.scalars(select(Role).where(Role.slug == LEO_DELEGATE_ROLE_SLUG))
    ).all()
    assert len(roles) == 1
    tags = set(
        await world.session.scalars(
            select(Action.tag)
            .join(RoleAction, RoleAction.action_id == Action.id)
            .where(RoleAction.role_id == world.delegate.id)
        )
    )
    assert tags == {TAG}
    assert LEO_DELEGATE_ROLE_SLUG in LEO_SERVICE_GRANTABLE_ROLE_SLUGS


async def test_admin_concede_el_rol_delegado_pero_no_leo_admin(world, admin):
    other = await make_client_app(world.session, slug="otra")
    await world.session.commit()
    url = f"/api/v1/applications/{other.app.id}/service-access"
    denied = await admin.post(
        url, json={"role_ids": [str((await leo_admin_role(world.session)).id)]}
    )
    assert denied.status_code == 422
    assert denied.json()["code"] == "leo_app_not_grantable"
    ok = await admin.post(url, json={"role_ids": [str(world.delegate.id)]})
    assert ok.status_code == 200, ok.text


# --- perfil ---


async def test_edita_nombres_200_con_perfil_minimo_y_audita_con_via(world):
    user = await world.patient(first_name="Ana", last_name="Gómez")
    token, _ = await world.user_token(user)

    response = await world.profile(token, first_name="Laura", last_name="Pérez")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "first_name": "Laura",
        "last_name": "Pérez",
        "email": user.email,
        "username": user.username,
    }
    fresh = await reload(world.session, user)
    assert (fresh.first_name, fresh.last_name) == ("Laura", "Pérez")
    [event] = await events(world.session, "leo.users.edit", actor_user_id=user.id)
    assert event.actor_username == user.username
    assert event.result == "ok"
    assert "via=servicio:acu" in event.reason
    assert event.changes["first_name"] == {"before": "Ana", "after": "Laura"}
    assert token not in str(event.changes) + (event.reason or "")


async def test_sin_cambios_reales_no_audita(world):
    user = await world.patient(first_name="Ana")
    token, _ = await world.user_token(user)
    response = await world.profile(token, first_name="Ana")
    assert response.status_code == 200
    assert await events(world.session, "leo.users.edit", actor_user_id=user.id) == []


async def test_cambiar_correo_sin_contrasena_422(world):
    user = await world.patient()
    token, _ = await world.user_token(user)
    response = await world.profile(token, email="nuevo@example.com")
    assert response.status_code == 422
    assert response.json()["code"] == "current_password_required"
    assert (await reload(world.session, user)).email == user.email


async def test_correo_con_contrasena_incorrecta_403_y_evento_denied(world):
    user = await world.patient()
    token, _ = await world.user_token(user)
    response = await world.profile(token, email="nuevo@example.com", current_password=WRONG)
    assert response.status_code == 403
    assert response.json()["code"] == "invalid_current_password"
    [event] = await events(world.session, "leo.users.edit", result="denied")
    assert event.actor_user_id == user.id
    assert "via=servicio:acu" in event.reason
    assert WRONG not in str(event.__dict__)
    assert (await reload(world.session, user)).email == user.email


async def test_correo_con_contrasena_correcta_cambia_y_cierra_otras_sesiones(world):
    user = await world.patient()
    token, _ = await world.user_token(user)
    await world.user_token(user)  # segunda sesion SSO
    sessions = list(
        await world.session.scalars(select(Session).where(Session.user_id == user.id))
    )
    assert len(sessions) == 2

    response = await world.profile(
        token, email="nuevo@example.com", current_password=STRONG_PASSWORD
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "nuevo@example.com"
    alive = {
        s.id: s.revoked_reason
        for s in await world.session.scalars(
            select(Session)
            .where(Session.user_id == user.id)
            .execution_options(populate_existing=True)
        )
    }
    reasons = sorted(str(r) for r in alive.values())
    assert sum(r is None for r in alive.values()) == 1  # la del token sigue viva
    assert SessionRevokedReason.EMAIL_CHANGE in alive.values()
    assert len(reasons) == 2
    [event] = await events(world.session, "leo.users.edit", result="ok", actor_user_id=user.id)
    assert "via=servicio:acu" in event.reason


async def test_correo_duplicado_409(world):
    other = await make_user(world.session, email="ocupado@example.com")
    assert other
    user = await world.patient()
    token, _ = await world.user_token(user)
    response = await world.profile(
        token, email="ocupado@example.com", current_password=STRONG_PASSWORD
    )
    assert response.status_code == 409
    assert response.json()["code"] == "duplicate"


# --- contrasena ---


async def test_cambia_contrasena_204_cierra_otras_sesiones_y_audita(world, make_browser):
    user = await world.patient()
    token, _ = await world.user_token(user)
    await world.user_token(user)  # segunda sesion

    response = await world.password(token)

    assert response.status_code == 204, response.text
    assert response.content == b""
    states = list(
        await world.session.scalars(
            select(Session)
            .where(Session.user_id == user.id)
            .execution_options(populate_existing=True)
        )
    )
    assert sum(s.revoked_at is None for s in states) == 1
    assert any(s.revoked_reason == SessionRevokedReason.PASSWORD_CHANGE for s in states)
    login = await make_browser().login(user.username, NEW_PASSWORD)
    assert login.status_code == 200
    assert (await make_browser().login(user.username, STRONG_PASSWORD)).status_code == 401
    [event] = await events(world.session, "leo.users.reset-password", result="ok")
    assert event.actor_user_id == user.id
    assert "via=servicio:acu" in event.reason
    dump = str(event.__dict__)
    assert NEW_PASSWORD not in dump and STRONG_PASSWORD not in dump and "argon2" not in dump


async def test_contrasena_actual_incorrecta_401_y_evento_denied(world):
    user = await world.patient()
    token, _ = await world.user_token(user)
    response = await world.password(token, current=WRONG)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    [event] = await events(world.session, "leo.users.reset-password", result="denied")
    assert "via=servicio:acu" in event.reason
    assert WRONG not in str(event.__dict__)


async def test_contrasena_debil_y_repetida_422(world):
    user = await world.patient()
    token, _ = await world.user_token(user)
    weak = await world.password(token, new="123")
    assert weak.status_code == 422
    assert weak.json()["code"] == "weak_password"
    same = await world.password(token, new=STRONG_PASSWORD)
    assert same.status_code == 422
    assert same.json()["code"] == "same_password"


async def test_fallos_por_la_via_delegada_bloquean_tambien_la_cookie_429(world):
    user = await world.patient()
    token, nav = await world.user_token(user)
    headers = await world.service_headers()

    for _ in range(5):  # LEO_LOGIN_MAX_FAILED_ATTEMPTS en los tests
        assert (await world.password(token, current=WRONG, headers=headers)).status_code == 401
    blocked = await world.password(token, headers=headers)
    cookie = await nav.post(
        "/api/v1/auth/me/password",
        json={"current_password": STRONG_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_attempts"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert cookie.status_code == 429


async def test_fallos_de_correo_delegados_comparten_bloqueo_con_la_contrasena(world):
    user = await world.patient()
    token, _ = await world.user_token(user)
    headers = await world.service_headers()
    for _ in range(5):
        r = await world.profile(
            token, headers=headers, email="x@example.com", current_password=WRONG
        )
        assert r.status_code == 403
    assert (await world.password(token, headers=headers)).status_code == 429


# --- restricciones de seguridad ---


async def test_usuario_con_permisos_leo_rechazado_403_generico_y_denied(world):
    user = await make_user(world.session)
    await grant(world.session, user, world.app_role)
    await grant(world.session, user, await leo_admin_role(world.session))
    token, _ = await world.user_token(user)

    response = await world.profile(token, first_name="Hackeado")
    pw = await world.password(token)

    for r in (response, pw):
        assert r.status_code == 403
        assert r.json()["code"] == "forbidden"
    assert (await reload(world.session, user)).first_name == user.first_name
    denied = await events(world.session, TAG, result="denied")
    assert len(denied) == 2
    assert all(e.actor_user_id == user.id for e in denied)


async def test_usuario_con_rol_de_leo_sin_acciones_tambien_rechazado(world):
    leo = await leo_app(world.session)
    empty = await make_role(world.session, leo.id)
    user = await world.patient()
    await grant(world.session, user, empty)
    token, _ = await world.user_token(user)
    assert (await world.profile(token, first_name="X")).status_code == 403


async def test_token_de_usuario_de_otra_app_401(world):
    other = await make_client_app(world.session, slug="otra-app", tags=["items.view"])
    other_role = await make_role(world.session, other.app.id, ["otra-app.items.view"])
    user = await make_user(world.session)
    await grant(world.session, user, other_role)
    token, _ = await world.user_token(user, app=other)

    response = await world.profile(token, first_name="X")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert (await reload(world.session, user)).first_name == user.first_name


async def test_usuario_sin_rol_activo_en_la_app_401(world):
    user = await world.patient()
    token, _ = await world.user_token(user)
    world.app_role.is_active = False
    await world.session.commit()
    assert (await world.profile(token, first_name="X")).status_code == 401


async def test_token_revocado_por_logout_401(world):
    user = await world.patient()
    token, nav = await world.user_token(user)
    assert (await nav.post("/api/v1/auth/logout")).status_code == 204
    response = await world.profile(token, first_name="X")
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert (await world.password(token)).status_code == 401


async def test_token_vencido_401(world, monkeypatch):
    user = await world.patient()
    token, _ = await world.user_token(user)
    later = clock.now() + timedelta(minutes=20)  # access dura 15 min
    monkeypatch.setattr(clock, "now", lambda: later)
    response = await world.profile(token, first_name="X")
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


async def test_token_inventado_o_de_servicio_401_generico(world):
    headers = await world.service_headers()
    service_token = headers["Authorization"].split()[1]
    for fake in ("no-existe", service_token):
        response = await world.profile(fake, headers=headers, first_name="X")
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_token"
        assert response.json()["details"] == {"field": "user_access_token"}


async def test_sin_el_tag_de_servicio_403(world):
    leo = await leo_app(world.session)
    caller = await make_client_app(world.session, slug="sin-tag")
    from app.core.db.seeds.leo_app import seed_leo_provisioner_role

    conn = await world.session.connection()
    await conn.run_sync(lambda sync: seed_leo_provisioner_role(sync, leo.id))
    provisioner = (
        await world.session.scalars(
            select(Role).where(Role.application_id == leo.id, Role.slug == "leo-patient-provisioner")
        )
    ).one()
    await grant_service_access(world.session, caller.app, provisioner)
    await world.session.commit()
    user = await world.patient()
    token, _ = await world.user_token(user)

    headers = await world.service_headers(caller)
    response = await world.profile(token, headers=headers, first_name="X")

    assert response.status_code == 403
    assert (await world.password(token, headers=headers)).status_code == 403
    assert (await reload(world.session, user)).first_name == user.first_name


async def test_sin_bearer_o_con_bearer_invalido_401(world):
    user = await world.patient()
    token, nav = await world.user_token(user)
    body = {"user_access_token": token, "first_name": "X"}
    assert (await world.client.patch(PROFILE, json=body)).status_code == 401
    bad = await world.client.patch(PROFILE, json=body, headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401
    assert bad.headers["WWW-Authenticate"] == "Bearer"
    # La cookie de sesion del usuario tampoco sirve en esta ruta.
    cookie = await nav.patch(PROFILE, json=body)
    assert cookie.status_code == 401


async def test_nunca_acepta_user_id_del_cliente(world):
    victim = await make_user(world.session, first_name="Victima")
    user = await world.patient()
    token, _ = await world.user_token(user)
    headers = await world.service_headers()

    for extra in ({"user_id": str(victim.id)}, {"username": victim.username}, {"id": str(victim.id)}):
        r = await world.client.patch(
            PROFILE,
            json={"user_access_token": token, "first_name": "Hack", **extra},
            headers=headers,
        )
        assert r.status_code == 422
    r = await world.client.post(
        PASSWORD,
        json={
            "user_access_token": token,
            "current_password": STRONG_PASSWORD,
            "new_password": NEW_PASSWORD,
            "user_id": str(victim.id),
        },
        headers=headers,
    )
    assert r.status_code == 422
    assert (await reload(world.session, victim)).first_name == "Victima"
    assert (await reload(world.session, user)).first_name == user.first_name


async def test_el_token_de_un_usuario_solo_edita_a_ese_usuario(world):
    a = await world.patient(first_name="A")
    b = await world.patient(first_name="B")
    token_a, _ = await world.user_token(a)
    await world.user_token(b)
    response = await world.profile(token_a, first_name="Nuevo")
    assert response.json()["username"] == a.username
    assert (await reload(world.session, b)).first_name == "B"


async def test_cuerpo_invalido_422_sin_eco_de_contrasenas(world):
    user = await world.patient()
    token, _ = await world.user_token(user)
    r = await world.client.post(
        PASSWORD,
        json={"user_access_token": token, "current_password": STRONG_PASSWORD},
        headers=await world.service_headers(),
    )
    assert r.status_code == 422
    assert STRONG_PASSWORD not in r.text


# --- rate limit ---


async def test_rate_limit_por_app_llamadora_429(world):
    user = await world.patient()
    token, _ = await world.user_token(user)
    await set_setting(world.session, "rate_limit.delegated_app_per_window", 10)
    headers = await world.service_headers()

    codes = [(await world.profile(token, headers=headers, first_name="Z")).status_code for _ in range(11)]

    assert codes == [200] * 10 + [429]
    last = await world.profile(token, headers=headers, first_name="Z")
    assert int(last.headers["Retry-After"]) >= 1


async def test_rate_limit_por_usuario_429_sin_afectar_a_otro(world):
    a = await world.patient()
    b = await world.patient()
    token_a, _ = await world.user_token(a)
    token_b, _ = await world.user_token(b)
    await set_setting(world.session, "rate_limit.delegated_user_per_window", 10)
    headers = await world.service_headers()

    for _ in range(10):
        assert (await world.profile(token_a, headers=headers, first_name="Z")).status_code == 200
    limited = await world.profile(token_a, headers=headers, first_name="Y")
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
    rb = await world.profile(token_b, headers=headers, first_name="Z")
    assert rb.status_code == 200, rb.text
