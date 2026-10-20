"""Admin de usuarios: politica de contrasena, unicidad, bloqueo, roles,
desactivacion (revoca sesiones) y auditoria sin secretos."""

from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.auth.models import Session
from app.testkit import (
    STRONG_PASSWORD,
    leo_admin_role,
    make_client_app,
    make_role,
    make_user,
)

USERS = "/api/v1/users"


def new_user(username: str = "maria.perez", **extra) -> dict:
    return {
        "username": username,
        "email": f"{username}@example.com",
        "password": STRONG_PASSWORD,
        "document_type": "CC",
        "document_number": "1234-5",
        "first_name": "María",
        "last_name": "Pérez",
        **extra,
    }


async def test_crear_usuario_no_expone_el_hash_y_audita_sin_secretos(session, admin):
    response = await admin.post(USERS, json=new_user("Maria.Perez"))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["username"] == "maria.perez"
    assert "password" not in response.text
    event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action_tag == "leo.users.create",
            AuditEvent.entity_id == body["id"],
        )
    )
    assert event.changes["username"]["after"] == "maria.perez"
    assert not any("password" in k for k in event.changes)


async def test_contrasena_debil_422_con_motivos(admin):
    response = await admin.post(USERS, json=new_user(password="corta"))
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "weak_password"
    assert "debe incluir una mayúscula" in body["details"]["password"]


async def test_contrasena_que_contiene_el_usuario_se_rechaza(admin):
    response = await admin.post(
        USERS, json=new_user("carlos", password="Carlos-Secreto-2026!")
    )
    assert response.status_code == 422


async def test_email_duplicado_sin_distinguir_mayusculas(admin):
    await admin.post(USERS, json=new_user("uno", email="dup@example.com"))
    response = await admin.post(
        USERS, json=new_user("dos", email="DUP@example.com", document_number="999")
    )
    assert response.status_code == 409
    assert response.json()["details"] == {"email": "DUP@example.com"}


async def test_documento_duplicado(admin):
    await admin.post(USERS, json=new_user("uno"))
    response = await admin.post(USERS, json=new_user("dos"))
    assert response.status_code == 409
    assert response.json()["details"]["document_number"] == "CC 1234-5"


async def test_username_con_arroba_se_rechaza(admin):
    response = await admin.post(USERS, json=new_user("a@b"))
    assert response.status_code == 422


async def test_editar_y_no_renombrar_usuario(session, admin):
    user = (await admin.post(USERS, json=new_user())).json()
    ok = await admin.patch(f"{USERS}/{user['id']}", json={"first_name": "Mariana"})
    assert ok.status_code == 200 and ok.json()["first_name"] == "Mariana"
    rename = await admin.patch(f"{USERS}/{user['id']}", json={"username": "otra"})
    assert rename.status_code == 422


async def test_no_puede_desactivarse_a_si_mismo(admin):
    response = await admin.post(f"{USERS}/{admin.user.id}/deactivate")
    assert response.status_code == 409
    assert response.json()["code"] == "self_deactivation"


async def test_desbloquear(session, admin, browser):
    user = await make_user(session)
    await session.commit()
    for _ in range(5):
        await browser.login(user.username, "Clave-Incorrecta-9!")
    assert (await browser.login(user.username)).status_code == 429
    response = await admin.post(f"{USERS}/{user.id}/unlock")
    assert response.status_code == 200
    assert response.json()["locked_until"] is None
    assert (await browser.login(user.username)).status_code == 200


async def test_reset_password_revoca_sesiones_y_aplica_politica(
    session, admin, browser
):
    user = await make_user(session)
    await session.commit()
    assert (await browser.login(user.username)).status_code == 200

    weak = await admin.post(
        f"{USERS}/{user.id}/reset-password", json={"password": "123"}
    )
    assert weak.status_code == 422
    new_password = "Otra-Clave-Fuerte-77#"
    response = await admin.post(
        f"{USERS}/{user.id}/reset-password", json={"password": new_password}
    )
    assert response.status_code == 200, response.text
    sso = await session.scalar(
        select(Session)
        .where(Session.user_id == user.id)
        .execution_options(populate_existing=True)
    )
    assert sso.revoked_reason == "admin"
    assert (await browser.get("/api/v1/auth/me")).status_code == 401
    assert (await browser.login(user.username, new_password)).status_code == 200


async def test_asignar_y_quitar_roles(session, admin):
    app = await make_client_app(session, tags=["x.view"])
    role = await make_role(session, app.app.id, [f"{app.app.slug}.x.view"])
    user = await make_user(session)
    await session.commit()

    added = await admin.post(
        f"{USERS}/{user.id}/roles", json={"role_ids": [str(role.id)]}
    )
    assert added.status_code == 200, added.text
    assert [r["slug"] for r in added.json()["roles"]] == [role.slug]
    again = await admin.post(
        f"{USERS}/{user.id}/roles", json={"role_ids": [str(role.id)]}
    )
    assert len(again.json()["roles"]) == 1

    removed = await admin.delete(f"{USERS}/{user.id}/roles/{role.id}")
    assert removed.json()["roles"] == []
    events = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action_tag == "leo.users.assign-roles",
                AuditEvent.entity_id == str(user.id),
            )
        )
    )
    assert len(events) == 2


async def test_rol_inexistente_422(session, admin):
    user = await make_user(session)
    await session.commit()
    response = await admin.post(
        f"{USERS}/{user.id}/roles",
        json={"role_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_reference"


async def test_listado_con_busqueda(session, admin):
    await make_user(session, first_name="Zacarías", username="zacarias-x")
    await session.commit()
    page = (await admin.get(f"{USERS}?q=zacar")).json()
    assert [u["username"] for u in page["items"]] == ["zacarias-x"]


async def test_usuario_inexistente_404_legible(admin):
    response = await admin.get(f"{USERS}/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["message"].startswith("No existe un usuario con id")


async def test_detalle_incluye_roles(session, admin):
    detail = (await admin.get(f"{USERS}/{admin.user.id}")).json()
    assert [r["slug"] for r in detail["roles"]] == [
        (await leo_admin_role(session)).slug
    ]
