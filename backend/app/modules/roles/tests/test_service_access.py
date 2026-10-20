"""Administracion de las concesiones entre aplicaciones (`service_grants`):
que roles de que apps tiene concedidos una app llamadora."""

import pytest
from sqlalchemy import select

from app.conftest import login_as
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import ServiceToken
from app.modules.roles.models import ServiceGrant
from app.testkit import (
    grant_service_access,
    leo_admin_role,
    make_client_app,
    make_role,
    make_user,
)

APPS = "/api/v1/applications"
TOKEN = "/api/v1/auth/token"
INTROSPECT = "/api/v1/auth/introspect"


def url(app_id, role_id=None) -> str:
    base = f"{APPS}/{app_id}/service-access"
    return base if role_id is None else f"{base}/{role_id}"


class World:
    def __init__(
        self, session, client, admin, caller, vlad, tauro, r_view, r_edit, r_tauro
    ):
        self.session, self.client, self.admin = session, client, admin
        self.caller, self.vlad, self.tauro = caller, vlad, tauro
        self.r_view, self.r_edit, self.r_tauro = r_view, r_edit, r_tauro

    async def issue(self, audience: str) -> str:
        response = await self.client.post(
            TOKEN,
            json={"grant_type": "client_credentials", "audience": audience},
            headers=self.caller.basic(),
        )
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    async def active(self, token: str, creds) -> bool:
        response = await self.client.post(
            INTROSPECT, json={"token": token}, headers=creds.basic()
        )
        assert response.status_code == 200, response.text
        return response.json()["active"]


@pytest.fixture
async def world(session, client, admin) -> World:
    caller = await make_client_app(session, slug="incubus")
    vlad = await make_client_app(
        session, slug="vlad", tags=["catalog.view", "samples.view", "samples.edit"]
    )
    tauro = await make_client_app(session, slug="tauro", tags=["caja.view"])
    r_view = await make_role(
        session, vlad.app.id, ["vlad.catalog.view"], slug="viewer", name="Lector"
    )
    r_edit = await make_role(
        session, vlad.app.id, ["vlad.samples.edit"], slug="editor", name="Editor"
    )
    r_tauro = await make_role(session, tauro.app.id, ["tauro.caja.view"])
    await session.commit()
    return World(session, client, admin, caller, vlad, tauro, r_view, r_edit, r_tauro)


async def events(session, caller_id) -> list[AuditEvent]:
    return list(
        (
            await session.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.action_tag == "leo.applications.grant-service-access",
                    AuditEvent.entity_id == str(caller_id),
                )
                .order_by(AuditEvent.id)
            )
        ).all()
    )


# --- listar / conceder ---


async def test_listado_vacio(world: World):
    response = await world.admin.get(url(world.caller.app.id))
    assert response.status_code == 200
    assert response.json() == []


async def test_conceder_y_listar_con_permisos_legibles(world: World):
    response = await world.admin.post(
        url(world.caller.app.id),
        json={"role_ids": [str(world.r_view.id), str(world.r_tauro.id)]},
    )
    assert response.status_code == 200, response.text
    grants = {g["application"]["slug"]: g for g in response.json()}
    assert set(grants) == {"vlad", "tauro"}
    vlad = grants["vlad"]
    assert vlad["role"] == {
        "id": str(world.r_view.id),
        "slug": "viewer",
        "name": "Lector",
        "is_active": True,
    }
    assert vlad["application"]["id"] == str(world.vlad.app.id)
    assert vlad["application"]["name"] == "App vlad"
    assert [a["tag"] for a in vlad["permissions"]] == ["vlad.catalog.view"]
    assert vlad["permissions"][0]["name"] == "View"
    assert vlad["permissions"][0]["module"]["slug"] == "catalog"
    assert {"id", "created_at"} <= set(vlad)
    again = await world.admin.get(url(world.caller.app.id))
    assert again.json() == response.json()


async def test_conceder_es_idempotente_y_sin_repetidos(world: World, session):
    body = {"role_ids": [str(world.r_view.id), str(world.r_view.id)]}
    first = await world.admin.post(url(world.caller.app.id), json=body)
    second = await world.admin.post(url(world.caller.app.id), json=body)
    assert first.status_code == second.status_code == 200
    assert len(second.json()) == 1
    assert len((await session.scalars(select(ServiceGrant))).all()) == 1
    assert len(await events(session, world.caller.app.id)) == 1  # el 2o no cambia nada


async def test_conceder_audita_con_diff_antes_despues(world: World, session):
    await world.admin.post(
        url(world.caller.app.id), json={"role_ids": [str(world.r_view.id)]}
    )
    await world.admin.post(
        url(world.caller.app.id), json={"role_ids": [str(world.r_edit.id)]}
    )
    first, second = await events(session, world.caller.app.id)
    assert first.actor_user_id == world.admin.user.id
    assert first.entity_type == "application"
    assert first.changes == {"service_roles": {"before": [], "after": ["vlad:viewer"]}}
    assert second.changes["service_roles"] == {
        "before": ["vlad:viewer"],
        "after": ["vlad:editor", "vlad:viewer"],
    }


async def test_rol_de_la_misma_app_error_legible_no_23514(world: World):
    own = await make_role(world.session, world.caller.app.id, [])
    await world.session.commit()
    response = await world.admin.post(
        url(world.caller.app.id), json={"role_ids": [str(own.id)]}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "same_application"
    assert "otra aplicación" in body["message"]
    assert body["details"]["role_ids"] == [str(own.id)]
    assert (await world.admin.get(url(world.caller.app.id))).json() == []


async def test_rol_inexistente_422(world: World):
    from uuid import uuid4

    ghost = str(uuid4())
    response = await world.admin.post(
        url(world.caller.app.id), json={"role_ids": [str(world.r_view.id), ghost]}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_reference"
    assert response.json()["details"]["role_ids"] == [ghost]
    # todo o nada: el valido tampoco se concedio
    assert (await world.admin.get(url(world.caller.app.id))).json() == []


async def test_rol_inactivo_422(world: World, session):
    world.r_edit.is_active = False
    await session.commit()
    response = await world.admin.post(
        url(world.caller.app.id), json={"role_ids": [str(world.r_edit.id)]}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "role_inactive"


async def test_no_se_concede_acceso_a_leo(world: World, session):
    leo_role = await leo_admin_role(session)
    response = await world.admin.post(
        url(world.caller.app.id), json={"role_ids": [str(leo_role.id)]}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "leo_app_not_grantable"


async def test_cuerpo_invalido_422(world: World):
    for body in (
        {},
        {"role_ids": []},
        {"role_ids": ["x"]},
        {"role_ids": ["a"], "x": 1},
    ):
        response = await world.admin.post(url(world.caller.app.id), json=body)
        assert response.status_code == 422


async def test_app_inexistente_404(world: World):
    from uuid import uuid4

    ghost = uuid4()
    assert (await world.admin.get(url(ghost))).status_code == 404
    assert (
        await world.admin.post(url(ghost), json={"role_ids": [str(world.r_view.id)]})
    ).status_code == 404
    assert (await world.admin.delete(url(ghost, world.r_view.id))).status_code == 404


# --- retirar ---


async def test_retirar_concesion_audita_y_devuelve_el_resto(world: World, session):
    await world.admin.post(
        url(world.caller.app.id),
        json={"role_ids": [str(world.r_view.id), str(world.r_edit.id)]},
    )
    response = await world.admin.delete(url(world.caller.app.id, world.r_view.id))
    assert response.status_code == 200, response.text
    assert [g["role"]["slug"] for g in response.json()] == ["editor"]
    last = (await events(session, world.caller.app.id))[-1]
    assert last.changes["service_roles"] == {
        "before": ["vlad:editor", "vlad:viewer"],
        "after": ["vlad:editor"],
    }


async def test_retirar_una_concesion_inexistente_404(world: World):
    response = await world.admin.delete(url(world.caller.app.id, world.r_view.id))
    assert response.status_code == 404


async def test_retirar_la_ultima_concesion_revoca_los_tokens_de_inmediato(
    world: World, session
):
    await world.admin.post(
        url(world.caller.app.id),
        json={"role_ids": [str(world.r_view.id), str(world.r_tauro.id)]},
    )
    to_vlad = await world.issue("vlad")
    to_tauro = await world.issue("tauro")
    assert await world.active(to_vlad, world.vlad)
    await world.admin.delete(url(world.caller.app.id, world.r_view.id))
    assert not await world.active(to_vlad, world.vlad)
    assert await world.active(to_tauro, world.tauro)  # otra audiencia: intacto
    rows = {
        r.audience_application_id: r
        for r in (
            await session.scalars(
                select(ServiceToken).execution_options(populate_existing=True)
            )
        ).all()
    }
    assert rows[world.vlad.app.id].revoked_at is not None
    assert rows[world.tauro.app.id].revoked_at is None
    # y no puede pedir otro
    again = await world.client.post(
        TOKEN,
        json={"grant_type": "client_credentials", "audience": "vlad"},
        headers=world.caller.basic(),
    )
    assert again.status_code == 403


async def test_retirar_un_rol_con_otro_vigente_no_revoca_y_recorta_permisos(
    world: World, session
):
    await world.admin.post(
        url(world.caller.app.id),
        json={"role_ids": [str(world.r_view.id), str(world.r_edit.id)]},
    )
    token = await world.issue("vlad")
    info = (
        await world.client.post(
            INTROSPECT, json={"token": token}, headers=world.vlad.basic()
        )
    ).json()
    assert info["permissions"] == ["vlad.catalog.view", "vlad.samples.edit"]
    await world.admin.delete(url(world.caller.app.id, world.r_view.id))
    info = (
        await world.client.post(
            INTROSPECT, json={"token": token}, headers=world.vlad.basic()
        )
    ).json()
    assert info["active"] is True
    assert info["permissions"] == ["vlad.samples.edit"]  # efecto inmediato


async def test_retirar_no_toca_los_tokens_de_otra_llamadora(world: World, session):
    other = await make_client_app(session, slug="acuarius")
    await grant_service_access(session, other.app, world.r_view)
    await world.admin.post(
        url(world.caller.app.id), json={"role_ids": [str(world.r_view.id)]}
    )
    resp = await world.client.post(
        TOKEN,
        json={"grant_type": "client_credentials", "audience": "vlad"},
        headers=other.basic(),
    )
    other_token = resp.json()["access_token"]
    await world.admin.delete(url(world.caller.app.id, world.r_view.id))
    assert await world.active(other_token, world.vlad)


# --- inverso: quien llama a un rol ---


async def test_service_callers_de_un_rol(world: World, session):
    other = await make_client_app(session, slug="acuarius")
    await grant_service_access(session, other.app, world.r_view)
    await world.admin.post(
        url(world.caller.app.id), json={"role_ids": [str(world.r_view.id)]}
    )
    response = await world.admin.get(f"/api/v1/roles/{world.r_view.id}/service-callers")
    assert response.status_code == 200, response.text
    callers = response.json()
    assert [c["application"]["slug"] for c in callers] == ["acuarius", "incubus"]
    assert set(callers[0]) == {"id", "application", "created_at"}
    assert set(callers[0]["application"]) == {"id", "slug", "name", "is_active"}
    empty = await world.admin.get(f"/api/v1/roles/{world.r_edit.id}/service-callers")
    assert empty.json() == []


async def test_service_callers_rol_inexistente_404(world: World):
    from uuid import uuid4

    response = await world.admin.get(f"/api/v1/roles/{uuid4()}/service-callers")
    assert response.status_code == 404


# --- permisos y ataques ---


async def test_todos_los_endpoints_exigen_el_tag(world: World, session, make_browser):
    """Un usuario con otros permisos `leo.*` pero no `grant-service-access`
    recibe 403 en los cuatro endpoints, y queda el evento `denied`."""
    from app.modules.users.models import UserRole

    viewer_role = await make_role(
        session,
        (await leo_admin_role(session)).application_id,
        ["leo.applications.view", "leo.roles.view", "leo.applications.edit"],
    )
    user = await make_user(session)
    session.add(UserRole(user_id=user.id, role_id=viewer_role.id))
    nav = await login_as(session, make_browser, user)
    caller, role = world.caller.app.id, world.r_view.id
    attempts = [
        await nav.get(url(caller)),
        await nav.post(url(caller), json={"role_ids": [str(role)]}),
        await nav.delete(url(caller, role)),
        await nav.get(f"/api/v1/roles/{role}/service-callers"),
    ]
    assert [r.status_code for r in attempts] == [403, 403, 403, 403]
    assert all(r.json()["code"] == "forbidden" for r in attempts)
    denied = (
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action_tag == "leo.applications.grant-service-access",
                AuditEvent.result == "denied",
                AuditEvent.actor_user_id == user.id,
            )
        )
    ).all()
    assert len(denied) == 4
    assert (await world.admin.get(url(caller))).json() == []  # nada se concedio


async def test_sin_sesion_401(world: World, make_browser):
    nav = make_browser()
    assert (await nav.get(url(world.caller.app.id))).status_code == 401
    assert (
        await nav.post(url(world.caller.app.id), json={"role_ids": []})
    ).status_code == 401
