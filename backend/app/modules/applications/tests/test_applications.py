"""Admin de aplicaciones, modulos y acciones; credenciales del cliente;
sincronizacion de catalogo; permisos y auditoria."""

from sqlalchemy import select, text

from app.conftest import login_as
from app.core.crypto import sha256_hex
from app.modules.audit.models import AuditEvent
from app.testkit import make_client_app, make_user

APPS = "/api/v1/applications"


def new_app(slug: str = "vladimir", **extra) -> dict:
    return {
        "slug": slug,
        "name": "Vladimir",
        "base_url": f"https://{slug}.test",
        "redirect_uris": [f"https://{slug}.test/auth/callback"],
        **extra,
    }


async def last_event(session, tag: str, entity_id: str) -> AuditEvent | None:
    return await session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action_tag == tag, AuditEvent.entity_id == entity_id)
        .order_by(AuditEvent.id.desc())
    )


async def test_crear_app_devuelve_el_secreto_una_sola_vez(session, admin, client):
    response = await admin.post(APPS, json=new_app())
    assert response.status_code == 201, response.text
    body = response.json()
    secret, app = body["client_secret"], body["application"]
    assert app["client_id"] == "vladimir" and len(secret) >= 43
    assert "client_secret_hash" not in app

    detail = await admin.get(f"{APPS}/{app['id']}")
    assert secret not in detail.text and "secret" not in detail.text

    stored = await session.scalar(
        text("SELECT client_secret_hash FROM applications WHERE id = :id"),
        {"id": app["id"]},
    )
    assert stored == sha256_hex(secret)

    event = await last_event(session, "leo.applications.create", app["id"])
    assert event.actor_user_id == admin.user.id
    assert event.changes["slug"] == {"before": None, "after": "vladimir"}
    assert not any("secret" in k or "hash" in k for k in event.changes)


async def test_slug_duplicado_409_legible(admin):
    await admin.post(APPS, json=new_app())
    response = await admin.post(APPS, json=new_app())
    assert response.status_code == 409
    assert response.json() == {
        "code": "duplicate",
        "message": "Ya existe una aplicación con el slug «vladimir».",
        "details": {"slug": "vladimir"},
    }


async def test_slug_invalido_422_legible(admin):
    response = await admin.post(APPS, json=new_app(slug="Con Espacios"))
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["details"][0]["field"] == "slug"
    assert body["details"][0]["message"] == "No tiene el formato esperado."


async def test_redirect_uri_con_fragmento_se_rechaza(admin):
    response = await admin.post(
        APPS, json=new_app(redirect_uris=["https://vladimir.test/cb#x"])
    )
    assert response.status_code == 422


async def test_no_se_puede_renombrar_el_slug(admin):
    app = (await admin.post(APPS, json=new_app())).json()["application"]
    response = await admin.patch(f"{APPS}/{app['id']}", json={"slug": "otro"})
    assert response.status_code == 422
    assert "no se puede cambiar" in response.json()["message"]


async def test_editar_audita_el_diff(session, admin):
    app = (await admin.post(APPS, json=new_app())).json()["application"]
    response = await admin.patch(f"{APPS}/{app['id']}", json={"name": "Vladimir LIS"})
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Vladimir LIS"
    event = await last_event(session, "leo.applications.edit", app["id"])
    assert event.changes == {"name": {"before": "Vladimir", "after": "Vladimir LIS"}}


async def test_nombre_nulo_en_patch_se_rechaza(admin):
    app = (await admin.post(APPS, json=new_app())).json()["application"]
    response = await admin.patch(f"{APPS}/{app['id']}", json={"name": None})
    assert response.status_code == 422


async def test_rotar_secreto_invalida_el_anterior(session, admin, client):
    created = (await admin.post(APPS, json=new_app())).json()
    app_id, old = created["application"]["id"], created["client_secret"]
    rotated = await admin.post(f"{APPS}/{app_id}/rotate-secret")
    assert rotated.status_code == 200
    new = rotated.json()["client_secret"]
    assert new != old

    body = {"token": "x", "jkt": "A" * 43}
    ok = await client.post("/api/v1/auth/introspect", json=body, auth=("vladimir", new))
    bad = await client.post(
        "/api/v1/auth/introspect", json=body, auth=("vladimir", old)
    )
    assert ok.status_code == 200 and bad.status_code == 401
    assert (
        await last_event(session, "leo.applications.rotate-secret", app_id) is not None
    )


async def test_la_app_leo_no_se_desactiva(session, admin):
    leo = (await admin.get(f"{APPS}?q=leo")).json()["items"][0]
    response = await admin.post(f"{APPS}/{leo['id']}/deactivate")
    assert response.status_code == 409
    assert response.json()["code"] == "leo_app_protected"


async def test_desactivar_y_reactivar_app(admin):
    app = (await admin.post(APPS, json=new_app())).json()["application"]
    off = await admin.post(f"{APPS}/{app['id']}/deactivate")
    assert off.json()["is_active"] is False
    on = await admin.post(f"{APPS}/{app['id']}/activate")
    assert on.json()["is_active"] is True


async def test_modulos_y_acciones_arman_el_tag(session, admin):
    app = (await admin.post(APPS, json=new_app())).json()["application"]
    module = await admin.post(
        f"{APPS}/{app['id']}/modules", json={"slug": "samples", "name": "Muestras"}
    )
    assert module.status_code == 201, module.text
    module_id = module.json()["id"]
    action = await admin.post(
        f"{APPS}/{app['id']}/modules/{module_id}/actions",
        json={"verb": "edit", "name": "Editar muestras"},
    )
    assert action.status_code == 201, action.text
    assert action.json()["tag"] == "vladimir.samples.edit"

    again = await admin.post(
        f"{APPS}/{app['id']}/modules/{module_id}/actions",
        json={"verb": "edit", "name": "Otro nombre"},
    )
    assert again.status_code == 409
    rename = await admin.patch(
        f"{APPS}/{app['id']}/actions/{action.json()['id']}", json={"verb": "update"}
    )
    assert rename.status_code == 422

    detail = (await admin.get(f"{APPS}/{app['id']}")).json()
    assert detail["modules"][0]["actions"][0]["tag"] == "vladimir.samples.edit"


async def test_modulo_de_otra_app_404(admin):
    a = (await admin.post(APPS, json=new_app("app-a"))).json()["application"]
    b = (await admin.post(APPS, json=new_app("app-b"))).json()["application"]
    module = (
        await admin.post(f"{APPS}/{a['id']}/modules", json={"slug": "m", "name": "M"})
    ).json()
    response = await admin.patch(
        f"{APPS}/{b['id']}/modules/{module['id']}", json={"name": "X"}
    )
    assert response.status_code == 404


async def test_listado_paginado_con_busqueda(admin):
    for slug in ("busca-uno", "busca-dos", "otra-cosa"):
        await admin.post(APPS, json=new_app(slug))
    page = (await admin.get(f"{APPS}?q=busca&page_size=1")).json()
    assert page["total"] == 2 and len(page["items"]) == 1


async def test_sin_permiso_403_y_evento_denied(session, make_browser):
    user = await make_user(session)
    nav = await login_as(session, make_browser, user)
    response = await nav.post(APPS, json=new_app())
    assert response.status_code == 403
    assert response.json()["message"] == "No tienes permiso para realizar esta acción."
    event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action_tag == "leo.applications.create",
            AuditEvent.result == "denied",
            AuditEvent.actor_user_id == user.id,
        )
    )
    assert event is not None


# --- sincronizacion de catalogo ---

CATALOG = {
    "modules": [
        {
            "slug": "samples",
            "name": "Muestras",
            "actions": [{"verb": "view"}, {"verb": "edit", "description": "Editar"}],
        },
        {"slug": "staff", "name": "Personal", "actions": [{"verb": "view"}]},
    ]
}


async def test_catalogo_se_sincroniza_y_es_idempotente(session, client):
    app = await make_client_app(session, slug="vlad")
    await session.commit()
    url, auth = f"{APPS}/vlad/catalog", ("vlad", app.secret)

    first = await client.put(url, json=CATALOG, auth=auth)
    assert first.status_code == 200, first.text
    assert sorted(first.json()["created_actions"]) == [
        "vlad.samples.edit",
        "vlad.samples.view",
        "vlad.staff.view",
    ]
    second = await client.put(url, json=CATALOG, auth=auth)
    assert all(v == [] for v in second.json().values())

    changed = {"modules": [{**CATALOG["modules"][0], "name": "Muestras de lab"}]}
    third = (
        await client.put(url, json={**changed, "deactivate_missing": True}, auth=auth)
    ).json()
    assert third["updated_modules"] == ["samples"]
    assert third["deactivated_modules"] == ["staff"]
    assert third["deactivated_actions"] == ["vlad.staff.view"]
    event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action_tag == "leo.applications.sync-catalog"
        )
    )
    assert event is not None


async def test_catalogo_de_otra_app_403(session, client):
    await make_client_app(session, slug="vlad")
    other = await make_client_app(session, slug="intruso")
    await session.commit()
    response = await client.put(
        f"{APPS}/vlad/catalog", json=CATALOG, auth=("intruso", other.secret)
    )
    assert response.status_code == 403
    assert response.json()["code"] == "client_mismatch"


async def test_catalogo_sin_credenciales_401(client):
    assert (await client.put(f"{APPS}/vlad/catalog", json=CATALOG)).status_code == 401


async def test_catalogo_con_verbos_repetidos_422(session, client):
    app = await make_client_app(session, slug="vlad")
    await session.commit()
    bad = {
        "modules": [
            {"slug": "m", "name": "M", "actions": [{"verb": "v"}, {"verb": "v"}]}
        ]
    }
    response = await client.put(
        f"{APPS}/vlad/catalog", json=bad, auth=("vlad", app.secret)
    )
    assert response.status_code == 422
    assert "repetidas" in response.json()["message"]
