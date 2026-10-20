"""Nombre legible de las acciones: alta, edicion, unicidad por modulo,
visibilidad en roles y sincronizacion de catalogo."""

import pytest
from sqlalchemy import select

from app.modules.applications.models import Action
from app.modules.audit.models import AuditEvent
from app.testkit import make_action, make_client_app, make_role

APPS = "/api/v1/applications"
ROLES = "/api/v1/roles"


async def app_with_module(admin, slug="vladimir"):
    app = (
        await admin.post(
            APPS,
            json={
                "slug": slug,
                "name": "Vladimir",
                "base_url": f"https://{slug}.test",
                "redirect_uris": [],
            },
        )
    ).json()["application"]
    module = (
        await admin.post(
            f"{APPS}/{app['id']}/modules", json={"slug": "samples", "name": "Muestras"}
        )
    ).json()
    return app, module


def actions_url(app, module):
    return f"{APPS}/{app['id']}/modules/{module['id']}/actions"


async def test_crear_accion_con_nombre(admin):
    app, module = await app_with_module(admin)
    response = await admin.post(
        actions_url(app, module),
        json={"verb": "view", "name": "  Consultar muestras  "},
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Consultar muestras"
    detail = (await admin.get(f"{APPS}/{app['id']}")).json()
    assert detail["modules"][0]["actions"][0]["name"] == "Consultar muestras"


async def test_crear_accion_sin_nombre_422(admin):
    app, module = await app_with_module(admin)
    response = await admin.post(actions_url(app, module), json={"verb": "view"})
    assert response.status_code == 422


@pytest.mark.parametrize("blank", ["", "   ", "\t\n ", "x" * 121])
async def test_nombre_en_blanco_o_largo_422(admin, blank):
    app, module = await app_with_module(admin)
    response = await admin.post(
        actions_url(app, module), json={"verb": "view", "name": blank}
    )
    assert response.status_code == 422


async def test_nombre_duplicado_en_el_modulo_409_legible(admin):
    app, module = await app_with_module(admin)
    await admin.post(
        actions_url(app, module), json={"verb": "view", "name": "Consultar"}
    )
    response = await admin.post(
        actions_url(app, module), json={"verb": "list", "name": "Consultar"}
    )
    assert response.status_code == 409
    assert response.json() == {
        "code": "duplicate",
        "message": "Ya existe una acción en este módulo con el nombre «Consultar».",
        "details": {"name": "Consultar"},
    }


async def test_mismo_nombre_en_otro_modulo_es_valido(admin):
    app, module = await app_with_module(admin)
    other = (
        await admin.post(
            f"{APPS}/{app['id']}/modules", json={"slug": "staff", "name": "Personal"}
        )
    ).json()
    for m in (module, other):
        response = await admin.post(
            actions_url(app, m), json={"verb": "view", "name": "Consultar"}
        )
        assert response.status_code == 201


async def test_editar_nombre_audita_before_after(session, admin):
    app, module = await app_with_module(admin)
    action = (
        await admin.post(actions_url(app, module), json={"verb": "view", "name": "Ver"})
    ).json()
    url = f"{APPS}/{app['id']}/actions/{action['id']}"
    response = await admin.patch(url, json={"name": "Consultar muestras"})
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Consultar muestras"
    assert response.json()["tag"] == action["tag"]
    event = await session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.action_tag == "leo.applications.edit",
            AuditEvent.entity_id == action["id"],
        )
        .order_by(AuditEvent.id.desc())
    )
    assert event.changes["name"] == {"before": "Ver", "after": "Consultar muestras"}

    assert (await admin.patch(url, json={"name": "  "})).status_code == 422
    assert (await admin.patch(url, json={"name": None})).status_code == 422
    assert (await admin.patch(url, json={"verb": "x"})).status_code == 422


async def test_editar_nombre_a_uno_repetido_409(admin):
    app, module = await app_with_module(admin)
    await admin.post(actions_url(app, module), json={"verb": "view", "name": "Uno"})
    second = (
        await admin.post(actions_url(app, module), json={"verb": "edit", "name": "Dos"})
    ).json()
    url = f"{APPS}/{app['id']}/actions/{second['id']}"
    response = await admin.patch(url, json={"name": "Uno"})
    assert response.status_code == 409
    assert response.json()["details"] == {"name": "Uno"}
    # conservar su propio nombre no es un duplicado
    assert (await admin.patch(url, json={"name": "Dos"})).status_code == 200


async def test_accion_de_evento_no_se_edita_409(session, admin):
    app = await make_client_app(session)
    action = await make_action(session, app.app, "audit.login")
    action.description = "Evento: inicio de sesión"
    await session.commit()
    response = await admin.patch(
        f"{APPS}/{app.app.id}/actions/{action.id}", json={"name": "Otro"}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "event_action_readonly"
    assert "evento" in response.json()["message"]


async def test_nombres_en_detalle_de_rol(session, admin):
    app = await make_client_app(session)
    view = await make_action(session, app.app, "items.view", name="Consultar items")
    edit = await make_action(session, app.app, "items.edit", name="Editar items")
    role = await make_role(session, app.app.id)
    await session.commit()
    added = await admin.post(
        f"{ROLES}/{role.id}/actions",
        json={"action_ids": [str(view.id), str(edit.id)]},
    )
    assert added.status_code == 200, added.text
    by_tag = {a["tag"]: a for a in added.json()["actions"]}
    assert by_tag[f"{app.app.slug}.items.view"] == {
        "id": str(view.id),
        "tag": f"{app.app.slug}.items.view",
        "verb": "view",
        "name": "Consultar items",
        "description": None,
        "is_active": True,
        "module": {"id": str(view.module_id), "slug": "items", "name": "items"},
    }
    detail = (await admin.get(f"{ROLES}/{role.id}")).json()
    assert {a["name"] for a in detail["actions"]} == {
        "Consultar items",
        "Editar items",
    }
    removed = await admin.delete(f"{ROLES}/{role.id}/actions/{edit.id}")
    assert [a["name"] for a in removed.json()["actions"]] == ["Consultar items"]


async def test_listado_de_acciones_asignables_trae_nombre_y_modulo(session, admin):
    app = await make_client_app(session)
    await make_action(session, app.app, "items.view", name="Consultar items")
    await session.commit()
    detail = (await admin.get(f"{APPS}/{app.app.id}")).json()
    module = detail["modules"][0]
    assert module["slug"] == "items" and module["name"] == "items"
    assert module["actions"][0]["name"] == "Consultar items"
    assert module["actions"][0]["verb"] == "view"


# --- sync-catalog ---


def catalog(*actions, module="samples"):
    return {"modules": [{"slug": module, "name": "Muestras", "actions": list(actions)}]}


async def stored(session, tag) -> Action:
    session.expire_all()
    return await session.scalar(select(Action).where(Action.tag == tag))


async def test_sync_crea_con_nombre_declarado_o_derivado(session, client):
    app = await make_client_app(session, slug="vlad")
    await session.commit()
    url, auth = f"{APPS}/vlad/catalog", ("vlad", app.secret)
    body = catalog(
        {"verb": "view", "name": "Consultar muestras"}, {"verb": "rotate-secret"}
    )
    assert (await client.put(url, json=body, auth=auth)).status_code == 200
    assert (await stored(session, "vlad.samples.view")).name == "Consultar muestras"
    derived = await stored(session, "vlad.samples.rotate-secret")
    assert derived.name == "Rotate secret"


async def test_sync_actualiza_solo_nombres_derivados(session, client, admin):
    app = await make_client_app(session, slug="vlad")
    app_id = app.app.id
    await session.commit()
    url, auth = f"{APPS}/vlad/catalog", ("vlad", app.secret)
    await client.put(url, json=catalog({"verb": "view"}, {"verb": "edit"}), auth=auth)

    # un admin edita el nombre de `edit`; `view` conserva el derivado
    edit = await stored(session, "vlad.samples.edit")
    renamed = await admin.patch(
        f"{APPS}/{app_id}/actions/{edit.id}", json={"name": "Modificar muestras"}
    )
    assert renamed.status_code == 200

    second = catalog(
        {"verb": "view", "name": "Consultar muestras"},
        {"verb": "edit", "name": "Nombre del codigo"},
    )
    result = (await client.put(url, json=second, auth=auth)).json()
    assert result["updated_actions"] == ["vlad.samples.view"]
    assert (await stored(session, "vlad.samples.view")).name == "Consultar muestras"
    assert (await stored(session, "vlad.samples.edit")).name == "Modificar muestras"

    again = (await client.put(url, json=second, auth=auth)).json()
    assert again["updated_actions"] == []


async def test_sync_nombre_repetido_409_legible(session, client):
    app = await make_client_app(session, slug="vlad")
    await session.commit()
    body = catalog(
        {"verb": "view", "name": "Consultar"}, {"verb": "list", "name": "Consultar"}
    )
    response = await client.put(
        f"{APPS}/vlad/catalog", json=body, auth=("vlad", app.secret)
    )
    assert response.status_code == 409
    assert response.json()["code"] == "duplicate"
    assert response.json()["details"] == {"name": "Consultar"}


async def test_sync_nombre_en_blanco_422(session, client):
    app = await make_client_app(session, slug="vlad")
    await session.commit()
    response = await client.put(
        f"{APPS}/vlad/catalog",
        json=catalog({"verb": "view", "name": "  "}),
        auth=("vlad", app.secret),
    )
    assert response.status_code == 422
