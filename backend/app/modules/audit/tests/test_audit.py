"""Auditoria: consulta con filtros, export CSV, ingesta de otras apps
(aislamiento por tag y actor validado)."""

import csv
import io

from sqlalchemy import select

from app.conftest import login_as
from app.core.tests.dpop_keys import DpopKey
from app.modules.audit.models import AuditEvent
from app.testkit import grant, make_client_app, make_role, make_user, pkce_pair

EVENTS = "/api/v1/audit/events"


async def test_listar_eventos_filtrados_y_paginados(session, admin):
    await admin.post(
        "/api/v1/applications",
        json={
            "slug": "filtro",
            "name": "F",
            "base_url": "https://f.test",
            "redirect_uris": [],
        },
    )
    page = (await admin.get(f"{EVENTS}?action_tag=leo.applications.create")).json()
    assert page["total"] == 1
    item = page["items"][0]
    assert item["actor_user_id"] == str(admin.user.id)
    assert item["module"] == "applications"
    assert item["result"] == "ok"
    by_actor = (
        await admin.get(f"{EVENTS}?actor_user_id={admin.user.id}&result=ok")
    ).json()
    assert by_actor["total"] >= 2  # login + creacion


async def test_rango_de_fechas_vacio(admin):
    page = (await admin.get(f"{EVENTS}?date_to=2000-01-01T00:00:00Z")).json()
    assert page["total"] == 0


async def test_listar_requiere_permiso(session, make_browser):
    nav = await login_as(session, make_browser, await make_user(session))
    assert (await nav.get(EVENTS)).status_code == 403


async def test_export_csv_neutraliza_formulas_y_se_audita(session, admin, client):
    app = await make_client_app(session, slug="hoja")
    await session.commit()
    await client.post(
        EVENTS,
        json={"action_tag": "hoja.m.v", "entity_id": "=HYPERLINK(1)"},
        auth=("hoja", app.secret),
    )
    response = await admin.get(f"{EVENTS}/export?action_tag=hoja.m.v")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["entity_id"] == "'=HYPERLINK(1)"
    assert rows[0]["application"] == "hoja"
    exported = await session.scalar(
        select(AuditEvent).where(AuditEvent.action_tag == "leo.audit.export")
    )
    assert exported is not None and exported.actor_user_id == admin.user.id


async def test_export_requiere_su_propio_permiso(session, make_browser):
    from app.testkit import leo_app

    leo = await leo_app(session)
    role = await make_role(session, leo.id, ["leo.audit.view"])
    user = await make_user(session)
    await grant(session, user, role)
    nav = await login_as(session, make_browser, user)
    assert (await nav.get(EVENTS)).status_code == 200
    assert (await nav.get(f"{EVENTS}/export")).status_code == 403


# --- ingesta desde las apps ---


async def test_app_solo_registra_tags_de_su_app(session, client):
    app = await make_client_app(session, slug="vlad")
    await session.commit()
    response = await client.post(
        EVENTS, json={"action_tag": "leo.users.create"}, auth=("vlad", app.secret)
    )
    assert response.status_code == 403
    assert response.json()["code"] == "foreign_action_tag"
    other = await client.post(
        EVENTS, json={"action_tag": "incubus.x.edit"}, auth=("vlad", app.secret)
    )
    assert other.status_code == 403


async def test_ingesta_sin_credenciales_401(client):
    assert (
        await client.post(EVENTS, json={"action_tag": "vlad.x.y"})
    ).status_code == 401


async def test_ingesta_con_actor_explicito_y_descarta_campos_sensibles(session, client):
    app = await make_client_app(session, slug="vlad", tags=["samples.edit"])
    role = await make_role(session, app.app.id, ["vlad.samples.edit"])
    user = await make_user(session)
    await grant(session, user, role)
    await session.commit()
    response = await client.post(
        EVENTS,
        json={
            "action_tag": "vlad.samples.edit",
            "actor_user_id": str(user.id),
            "entity_type": "sample",
            "entity_id": "S-1",
            "changes": {
                "status": {"before": "a", "after": "b"},
                "password": {"before": "x", "after": "y"},
            },
            "ip": "10.0.0.7",
        },
        auth=("vlad", app.secret),
    )
    assert response.status_code == 201, response.text
    event = await session.get(AuditEvent, response.json()["id"])
    assert event.application_id == app.app.id
    assert event.module == "samples"
    assert event.actor_username == user.username
    assert event.changes == {"status": {"before": "a", "after": "b"}}
    assert str(event.ip) == "10.0.0.7"


async def test_actor_sin_acceso_a_la_app_422(session, client):
    app = await make_client_app(session, slug="vlad")
    user = await make_user(session)
    await session.commit()
    response = await client.post(
        EVENTS,
        json={"action_tag": "vlad.x.edit", "actor_user_id": str(user.id)},
        auth=("vlad", app.secret),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_actor"


async def test_ingesta_con_token_del_usuario(session, client, make_browser):
    app = await make_client_app(session, slug="vlad", tags=["samples.edit"])
    role = await make_role(session, app.app.id, ["vlad.samples.edit"])
    user = await make_user(session)
    await grant(session, user, role)
    nav = await login_as(session, make_browser, user)
    device = DpopKey()
    verifier, challenge = pkce_pair()
    redirect = (
        await nav.post(
            "/api/v1/auth/authorize",
            json={
                "client_id": "vlad",
                "redirect_uri": app.app.redirect_uris[0],
                "state": "s",
                "code_challenge": challenge,
                "dpop_jkt": device.jkt,
            },
        )
    ).json()["redirect_to"]
    code = redirect.split("code=")[1].split("&")[0]
    tokens = (
        await client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": app.app.redirect_uris[0],
                "jkt": device.jkt,
            },
            auth=("vlad", app.secret),
        )
    ).json()

    ok = await client.post(
        EVENTS,
        json={
            "action_tag": "vlad.samples.edit",
            "actor": {"access_token": tokens["access_token"], "jkt": device.jkt},
        },
        auth=("vlad", app.secret),
    )
    assert ok.status_code == 201, ok.text
    event = await session.get(AuditEvent, ok.json()["id"])
    assert event.actor_user_id == user.id and event.session_id is not None

    stolen = await client.post(
        EVENTS,
        json={
            "action_tag": "vlad.samples.edit",
            "actor": {"access_token": tokens["access_token"], "jkt": DpopKey().jkt},
        },
        auth=("vlad", app.secret),
    )
    assert stolen.status_code == 422


async def test_ip_invalida_en_ingesta_422(session, client):
    app = await make_client_app(session, slug="vlad")
    await session.commit()
    response = await client.post(
        EVENTS,
        json={"action_tag": "vlad.x.y", "ip": "no-es-ip"},
        auth=("vlad", app.secret),
    )
    assert response.status_code == 422
