"""`description: null` explicito = sin descripcion; nunca 500 (regresion)."""

from app.testkit import make_client_app, make_role

APPS = "/api/v1/applications"
ROLES = "/api/v1/roles"
EVENTS = "/api/v1/audit/events"


async def test_catalogo_acepta_description_null(session, client):
    app = await make_client_app(session, slug="vlad")
    await session.commit()
    catalog = {
        "modules": [
            {
                "slug": "samples",
                "name": "Muestras",
                "description": None,
                "actions": [{"verb": "view", "description": None}],
            }
        ]
    }
    response = await client.put(
        f"{APPS}/vlad/catalog", json=catalog, auth=("vlad", app.secret)
    )
    assert response.status_code == 200, response.text


async def test_crud_de_apps_modulos_y_acciones_acepta_description_null(admin):
    created = await admin.post(
        APPS,
        json={
            "slug": "nul",
            "name": "Nul",
            "description": None,
            "base_url": "https://nul.test",
            "redirect_uris": [],
        },
    )
    assert created.status_code == 201, created.text
    app = created.json()["application"]
    assert app["description"] is None

    patched = await admin.patch(f"{APPS}/{app['id']}", json={"description": None})
    assert patched.status_code == 200, patched.text

    module = await admin.post(
        f"{APPS}/{app['id']}/modules",
        json={"slug": "m", "name": "M", "description": None},
    )
    assert module.status_code == 201, module.text
    module = module.json()
    patched = await admin.patch(
        f"{APPS}/{app['id']}/modules/{module['id']}", json={"description": None}
    )
    assert patched.status_code == 200, patched.text

    action = await admin.post(
        f"{APPS}/{app['id']}/modules/{module['id']}/actions",
        json={"verb": "view", "name": "Ver", "description": None},
    )
    assert action.status_code == 201, action.text
    patched = await admin.patch(
        f"{APPS}/{app['id']}/actions/{action.json()['id']}", json={"description": None}
    )
    assert patched.status_code == 200, patched.text


async def test_patch_description_null_borra_la_descripcion(admin):
    app = (
        await admin.post(
            APPS,
            json={
                "slug": "nul",
                "name": "Nul",
                "description": "algo",
                "base_url": "https://nul.test",
            },
        )
    ).json()["application"]
    patched = await admin.patch(f"{APPS}/{app['id']}", json={"description": None})
    assert patched.json()["description"] is None


async def test_roles_acepta_description_null(session, admin):
    app = await make_client_app(session)
    role = await make_role(session, app.app.id)
    await session.commit()
    created = await admin.post(
        ROLES,
        json={
            "application_id": str(app.app.id),
            "slug": "nul",
            "name": "Nul",
            "description": None,
        },
    )
    assert created.status_code == 201, created.text
    patched = await admin.patch(f"{ROLES}/{role.id}", json={"description": None})
    assert patched.status_code == 200, patched.text


async def test_ingesta_de_auditoria_acepta_campos_opcionales_null(session, client):
    app = await make_client_app(session, slug="vlad", tags=["samples.edit"])
    await session.commit()
    response = await client.post(
        EVENTS,
        json={
            "action_tag": "vlad.samples.edit",
            "entity_type": None,
            "entity_id": None,
            "reason": None,
            "user_agent": None,
            "request_id": None,
        },
        auth=("vlad", app.secret),
    )
    assert response.status_code != 500, response.text
