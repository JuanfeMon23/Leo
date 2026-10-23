"""Aprovisionamiento de pacientes: `POST /users/service/patients` con un token
de servicio (audiencia `leo`) de una app a la que se concedio el rol
`leo-patient-provisioner`; semilla de `acuarius` y su rol `paciente`."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core import clock
from app.core.db.seeds.acuarius_app import (
    ACUARIUS_MODULES,
    seed_acuarius_application,
)
from app.core.db.seeds.catalog import LEO_PROVISIONER_ROLE_SLUG
from app.core.db.seeds.leo_app import seed_leo_provisioner_role
from app.modules.applications.models import Action, Application
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import ServiceToken
from app.modules.roles.models import Role, RoleAction, ServiceGrant
from app.modules.users import controller
from app.modules.users.models import User, UserRole
from app.testkit import (
    STRONG_PASSWORD,
    grant_service_access,
    leo_app,
    make_client_app,
    make_role,
    set_setting,
    unique,
)

PATIENTS = "/api/v1/users/service/patients"
TOKEN = "/api/v1/auth/token"
TAG = "leo.users.provision-patient"
PATIENT_TAGS = {
    "acuarius.results.view",
    "acuarius.results.download",
    "acuarius.family.view",
    "acuarius.family.invite",
    "acuarius.family.respond",
    "acuarius.family.manage",
}


@pytest.fixture(autouse=True)
def _reset_limiter():
    controller._provision_limiter = None
    yield
    controller._provision_limiter = None


@pytest.fixture
async def world(session, client):
    """Seeds de `acuarius` y del rol aprovisionador + una app llamadora
    (`portal`) con ese rol concedido."""
    leo = await leo_app(session)
    conn = await session.connection()
    await conn.run_sync(lambda sync: seed_leo_provisioner_role(sync, leo.id))
    await conn.run_sync(seed_acuarius_application)
    caller = await make_client_app(session, slug="portal")
    provisioner = (
        await session.scalars(
            select(Role).where(
                Role.application_id == leo.id, Role.slug == LEO_PROVISIONER_ROLE_SLUG
            )
        )
    ).one()
    await grant_service_access(session, caller.app, provisioner)
    await session.commit()

    class World:
        pass

    w = World()
    w.session, w.client, w.caller, w.provisioner = session, client, caller, provisioner
    return w


async def bearer(world, creds=None, audience="leo") -> dict[str, str]:
    response = await world.client.post(
        TOKEN,
        json={"grant_type": "client_credentials", "audience": audience},
        headers=(creds or world.caller).basic(),
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def body(**overrides):
    suffix = unique("p").replace("-", "")
    data = {
        "username": f"pac{suffix}",
        "email": f"pac{suffix}@example.com",
        "password": STRONG_PASSWORD,
        "document_type": "CC",
        "document_number": suffix.upper(),
        "first_name": "Laura",
        "last_name": "Pérez",
    }
    data.update(overrides)
    return data


async def create(world, headers=None, **overrides):
    headers = headers if headers is not None else await bearer(world)
    return await world.client.post(PATIENTS, json=body(**overrides), headers=headers)


async def events(session, result=None):
    stmt = select(AuditEvent).where(AuditEvent.action_tag == TAG)
    if result:
        stmt = stmt.where(AuditEvent.result == result)
    return list((await session.scalars(stmt)).all())


# --- semilla ---


async def test_semilla_acuarius_y_rol_paciente(world):
    session = world.session
    app = (
        await session.scalars(select(Application).where(Application.slug == "acuarius"))
    ).one()
    assert app.client_id == "acuarius"
    assert app.base_url == "http://localhost:3300"
    assert app.redirect_uris == ["http://localhost:3300/leo/callback"]
    role = (
        await session.scalars(
            select(Role).where(Role.application_id == app.id, Role.slug == "paciente")
        )
    ).one()
    tags = set(
        await session.scalars(
            select(Action.tag)
            .join(RoleAction, RoleAction.action_id == Action.id)
            .where(RoleAction.role_id == role.id)
        )
    )
    assert tags == PATIENT_TAGS
    assert PATIENT_TAGS == {
        f"acuarius.{m}.{v}" for m, (_, verbs) in ACUARIUS_MODULES.items() for v in verbs
    }


async def test_semilla_idempotente(world):
    conn = await world.session.connection()
    await conn.run_sync(seed_acuarius_application)
    await conn.run_sync(
        lambda sync: seed_leo_provisioner_role(sync, world.provisioner.application_id)
    )
    roles = (
        await world.session.scalars(select(Role).where(Role.slug == "paciente"))
    ).all()
    assert len(roles) == 1


async def test_rol_aprovisionador_solo_tiene_la_accion_de_aprovisionar(world):
    tags = set(
        await world.session.scalars(
            select(Action.tag)
            .join(RoleAction, RoleAction.action_id == Action.id)
            .where(RoleAction.role_id == world.provisioner.id)
        )
    )
    assert tags == {TAG}


# --- camino feliz ---


async def test_crea_paciente_activo_con_rol_y_puede_iniciar_sesion(world, make_browser):
    data = body()
    response = await world.client.post(PATIENTS, json=data, headers=await bearer(world))
    assert response.status_code == 201, response.text
    out = response.json()
    assert set(out) == {
        "id",
        "username",
        "email",
        "document_type",
        "document_number",
        "first_name",
        "last_name",
        "is_active",
        "created_at",
    }
    assert out["is_active"] is True
    assert out["username"] == data["username"]
    assert "password" not in response.text and "argon2" not in response.text

    user = (
        await world.session.scalars(
            select(User).where(User.username == data["username"])
        )
    ).one()
    assert user.password_hash.startswith("$argon2id$")
    role_slugs = set(
        await world.session.scalars(
            select(Role.slug)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
    )
    assert role_slugs == {"paciente"}

    await world.session.commit()
    login = await make_browser().login(data["username"], data["password"])
    assert login.status_code == 200, login.text


async def test_audita_con_actor_servicio_sin_secretos(world):
    data = body()
    response = await create(world, **data)
    assert response.status_code == 201
    [event] = await events(world.session, "ok")
    assert event.actor_user_id is None
    assert event.actor_username == "servicio:portal"
    assert event.entity_type == "user"
    assert event.entity_id == response.json()["id"]
    assert "portal" in event.reason
    assert event.changes["role"]["after"] == "acuarius/paciente"
    assert event.changes["username"]["after"] == data["username"]
    assert data["password"] not in str(event.changes) + (event.reason or "")
    assert "hash" not in str(event.changes).lower()


async def test_no_acepta_roles_ni_campos_extra(world):
    for extra in ({"role_ids": ["x"]}, {"is_active": False}, {"roles": ["leo-admin"]}):
        response = await world.client.post(
            PATIENTS,
            json={**body(), **extra},
            headers=await bearer(world),
        )
        assert response.status_code == 422, extra
    assert await events(world.session) == []


# --- autenticacion ---


async def test_sin_bearer_401(world):
    response = await world.client.post(PATIENTS, json=body())
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header", ["Bearer", "Bearer basura", "Basic abc", "Token xyz", "bearer "]
)
async def test_bearer_invalido_401(world, header):
    response = await world.client.post(
        PATIENTS, json=body(), headers={"Authorization": header}
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_sesion_de_usuario_admin_no_sirve(world, admin):
    response = await admin.post(PATIENTS, json=body())
    assert response.status_code == 401
    # ni siquiera un admin con todos los permisos crea pacientes por esta ruta
    assert await events(world.session) == []


async def test_token_de_otra_audiencia_401(world):
    audience = await make_client_app(world.session, slug="vlad", tags=["catalog.view"])
    role = await make_role(world.session, audience.app.id, ["vlad.catalog.view"])
    await grant_service_access(world.session, world.caller.app, role)
    await world.session.commit()
    headers = await bearer(world, audience="vlad")
    response = await world.client.post(PATIENTS, json=body(), headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


async def test_sin_concesion_no_obtiene_token_para_leo(world):
    stranger = await make_client_app(world.session, slug="stranger")
    await world.session.commit()
    response = await world.client.post(
        TOKEN,
        json={"grant_type": "client_credentials", "audience": "leo"},
        headers=stranger.basic(),
    )
    assert response.status_code == 403


async def test_concesion_con_permiso_distinto_da_403_y_audita_denegado(world):
    leo = await leo_app(world.session)
    other = await make_client_app(world.session, slug="otra")
    view = (
        await world.session.scalars(
            select(Action).where(Action.tag == "leo.users.view")
        )
    ).one()
    role = await make_role(world.session, leo.id, [])
    world.session.add(
        RoleAction(role_id=role.id, action_id=view.id, application_id=leo.id)
    )
    await world.session.flush()
    await grant_service_access(world.session, other.app, role)
    await world.session.commit()

    response = await world.client.post(
        PATIENTS, json=body(), headers=await bearer(world, other)
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    [event] = await events(world.session, "denied")
    assert event.actor_username == "servicio:otra"
    assert event.actor_user_id is None


async def test_token_vencido_401(world):
    headers = await bearer(world)
    token = (await world.session.scalars(select(ServiceToken))).one()
    token.expires_at = clock.now() - timedelta(seconds=1)
    token.created_at = token.expires_at - timedelta(minutes=10)
    await world.session.commit()
    assert (await create(world, headers)).status_code == 401


async def test_quitar_la_concesion_corta_el_acceso_de_inmediato(world):
    headers = await bearer(world)
    assert (await create(world, headers)).status_code == 201
    await world.session.delete(
        (await world.session.scalars(select(ServiceGrant))).one()
    )
    await world.session.commit()
    assert (await create(world, headers)).status_code == 401


async def test_rol_aprovisionador_desactivado_401(world):
    headers = await bearer(world)
    world.provisioner.is_active = False
    await world.session.commit()
    assert (await create(world, headers)).status_code == 401


async def test_app_llamadora_desactivada_401(world):
    headers = await bearer(world)
    world.caller.app.is_active = False
    await world.session.commit()
    assert (await create(world, headers)).status_code == 401


# --- concesion por la API de administracion ---


async def test_admin_puede_conceder_solo_el_rol_aprovisionador(world, admin):
    from app.testkit import leo_admin_role

    other = await make_client_app(world.session, slug="nueva")
    await world.session.commit()
    url = f"/api/v1/applications/{other.app.id}/service-access"
    denied = await admin.post(
        url, json={"role_ids": [str((await leo_admin_role(world.session)).id)]}
    )
    assert denied.status_code == 422
    assert denied.json()["code"] == "leo_app_not_grantable"
    ok = await admin.post(url, json={"role_ids": [str(world.provisioner.id)]})
    assert ok.status_code == 200, ok.text


# --- duplicados: respuesta neutra ---


async def test_duplicados_dan_el_mismo_409_generico(world):
    first = body()
    assert (await create(world, **first)).status_code == 201
    variants = {
        "username": body(username=first["username"]),
        "email": body(email=first["email"].upper()),
        "documento": body(
            document_type=first["document_type"],
            document_number=first["document_number"],
        ),
    }
    bodies = set()
    for name, data in variants.items():
        response = await world.client.post(
            PATIENTS, json=data, headers=await bearer(world)
        )
        assert response.status_code == 409, name
        out = response.json()
        assert out["code"] == "conflict", name
        assert out["details"] is None, name
        assert first["username"] not in response.text, name
        bodies.add(response.text)
    assert len(bodies) == 1  # idéntica en los tres casos
    assert len(await events(world.session, "denied")) == 3


async def test_contrasena_debil_422(world):
    response = await create(world, password="corta")
    assert response.status_code == 422
    assert response.json()["code"] == "weak_password"


async def test_sin_rol_paciente_503(world):
    role = (
        await world.session.scalars(select(Role).where(Role.slug == "paciente"))
    ).one()
    role.is_active = False
    await world.session.commit()
    response = await create(world)
    assert response.status_code == 503
    assert response.json()["code"] == "patient_role_unavailable"
    assert (
        await world.session.scalars(
            select(User).where(User.document_type == "CC", User.first_name == "Laura")
        )
    ).all() == []


# --- rate limit ---


async def test_rate_limit_por_app_llamadora(world):
    await set_setting(world.session, "rate_limit.provision_per_window", 2)
    headers = await bearer(world)
    assert (await create(world, headers)).status_code == 201
    assert (await create(world, headers)).status_code == 201
    response = await create(world, headers)
    assert response.status_code == 429
    assert response.json()["code"] == "too_many_attempts"
    assert int(response.headers["retry-after"]) >= 1
    assert len(await events(world.session, "ok")) == 2
