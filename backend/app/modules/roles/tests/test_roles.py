"""Admin de roles: por aplicacion, acciones solo de su app, desactivar, y
efecto en los permisos efectivos."""

from sqlalchemy import select

from app.conftest import login_as
from app.modules.audit.models import AuditEvent
from app.modules.roles.models import RoleAction
from app.testkit import grant, make_action, make_client_app, make_role, make_user

ROLES = "/api/v1/roles"


async def test_crear_rol_y_asignar_acciones_de_su_app(session, admin):
    app = await make_client_app(session, tags=["items.view", "items.edit"])
    await session.commit()
    created = await admin.post(
        ROLES,
        json={"application_id": str(app.app.id), "slug": "editor", "name": "Editor"},
    )
    assert created.status_code == 201, created.text
    role_id = created.json()["id"]
    detail = (await admin.get(f"/api/v1/applications/{app.app.id}")).json()
    action_ids = [a["id"] for m in detail["modules"] for a in m["actions"]]

    added = await admin.post(
        f"{ROLES}/{role_id}/actions", json={"action_ids": action_ids}
    )
    assert added.status_code == 200, added.text
    assert sorted(a["tag"] for a in added.json()["actions"]) == sorted(
        f"{app.app.slug}.items.{v}" for v in ("edit", "view")
    )
    event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action_tag == "leo.roles.edit", AuditEvent.entity_id == role_id
        )
    )
    assert event.changes["actions"]["before"] == []


async def test_accion_de_otra_app_se_rechaza(session, admin):
    app = await make_client_app(session)
    other = await make_client_app(session)
    foreign = await make_action(session, other.app, "items.view")
    role = await make_role(session, app.app.id)
    await session.commit()
    response = await admin.post(
        f"{ROLES}/{role.id}/actions", json={"action_ids": [str(foreign.id)]}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_reference"
    assert (
        await session.scalar(select(RoleAction).where(RoleAction.role_id == role.id))
    ) is None


async def test_slug_de_rol_duplicado_en_la_misma_app(session, admin):
    app = await make_client_app(session)
    await session.commit()
    body = {"application_id": str(app.app.id), "slug": "lector", "name": "Lector"}
    await admin.post(ROLES, json=body)
    response = await admin.post(ROLES, json=body)
    assert response.status_code == 409


async def test_rol_con_app_inexistente_422(admin):
    response = await admin.post(
        ROLES,
        json={
            "application_id": "00000000-0000-0000-0000-000000000000",
            "slug": "x",
            "name": "X",
        },
    )
    assert response.status_code == 422


async def test_desactivar_rol_quita_el_acceso(session, admin, make_browser):
    app = await make_client_app(session, tags=["items.view"])
    role = await make_role(session, app.app.id, [f"{app.app.slug}.items.view"])
    user = await make_user(session)
    await grant(session, user, role)
    nav = await login_as(session, make_browser, user)
    assert [
        a["slug"] for a in (await nav.get("/api/v1/auth/me")).json()["applications"]
    ] == [app.app.slug]
    assert (await admin.post(f"{ROLES}/{role.id}/deactivate")).status_code == 200
    assert (await nav.get("/api/v1/auth/me")).json()["applications"] == []


async def test_quitar_accion_del_rol(session, admin):
    app = await make_client_app(session, tags=["items.view"])
    role = await make_role(session, app.app.id, [f"{app.app.slug}.items.view"])
    await session.commit()
    action_id = (await admin.get(f"{ROLES}/{role.id}")).json()["actions"][0]["id"]
    response = await admin.delete(f"{ROLES}/{role.id}/actions/{action_id}")
    assert response.status_code == 200
    assert response.json()["actions"] == []
    missing = await admin.delete(f"{ROLES}/{role.id}/actions/{action_id}")
    assert missing.status_code == 404


async def test_listar_roles_por_app(session, admin):
    app = await make_client_app(session)
    await make_role(session, app.app.id, slug="uno")
    await make_role(session, app.app.id, slug="dos")
    await session.commit()
    page = (await admin.get(f"{ROLES}?application_id={app.app.id}")).json()
    assert [r["slug"] for r in page["items"]] == ["dos", "uno"]


async def test_no_renombrar_slug_de_rol(session, admin):
    app = await make_client_app(session)
    role = await make_role(session, app.app.id)
    await session.commit()
    response = await admin.patch(f"{ROLES}/{role.id}", json={"slug": "nuevo"})
    assert response.status_code == 422


async def test_roles_requieren_permiso(session, make_browser):
    user = await make_user(session)
    nav = await login_as(session, make_browser, user)
    assert (await nav.get(ROLES)).status_code == 403
