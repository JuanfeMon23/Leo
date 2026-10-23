"""Exposicion minima para cuentas sin permisos `leo.*` (pacientes de
Acuarius): lo que Leo responde a un usuario autenticado no filtra roles,
apps ni permisos ajenos, ni ids internos innecesarios."""

import json

from app.conftest import login_as
from app.core.tests.dpop_keys import DpopKey
from app.testkit import grant, make_client_app, make_role, make_user, pkce_pair

ME = "/api/v1/auth/me"
SESSIONS = "/api/v1/auth/sessions"
AUTHORIZE = "/api/v1/auth/authorize"
INTROSPECT = "/api/v1/auth/introspect"
TAGS = [f"citas.accion{i}" for i in range(6)]
FOREIGN = ("secretapp", "rol-ajeno", "leo-admin", "leo.", "paciente")


async def patient(session, make_browser):
    """Paciente con 6 tags de `acuarius`; existen otra app y otro rol."""
    acuarius = await make_client_app(session, slug="acuarius", tags=TAGS)
    secret_app = await make_client_app(session, slug="secretapp", tags=["panel.ver"])
    await make_role(session, secret_app.app.id, ["secretapp.panel.ver"], slug="rol-ajeno")
    role = await make_role(
        session, acuarius.app.id, [f"acuarius.{t}" for t in TAGS], slug="paciente"
    )
    user = await make_user(session)
    await grant(session, user, role)
    return acuarius, user, await login_as(session, make_browser, user)


async def test_me_de_paciente_es_minimo(session, make_browser):
    _, _, nav = await patient(session, make_browser)

    body = (await nav.get(ME)).json()

    assert body["permissions"] == []  # ningun tag leo.*
    assert [a["slug"] for a in body["applications"]] == ["acuarius"]
    assert set(body["applications"][0]) == {"slug", "name", "base_url"}
    blob = json.dumps(body)
    for foreign in FOREIGN:
        assert foreign not in blob


async def test_403_no_revela_tags_ni_nombres_de_apps(session, make_browser):
    _, _, nav = await patient(session, make_browser)
    other = await make_client_app(session, slug="otraapp", tags=["x.y"])

    sessions = await nav.get(SESSIONS)
    users = await nav.get("/api/v1/users")
    _, challenge = pkce_pair()
    denied = await nav.post(
        AUTHORIZE,
        json={
            "client_id": other.client_id,
            "redirect_uri": other.app.redirect_uris[0],
            "state": "s",
            "code_challenge": challenge,
            "dpop_jkt": DpopKey().jkt,
        },
    )

    for response in (sessions, users):
        assert response.status_code == 403
        assert response.json()["code"] == "forbidden"
        assert not response.json().get("details")
        assert "leo." not in response.text
    assert denied.status_code == 403
    assert denied.json()["code"] == "access_denied"
    assert other.app.name not in denied.text


async def test_introspect_de_paciente_solo_tags_y_apps_propios(
    session, client, make_browser
):
    acuarius, _, nav = await patient(session, make_browser)
    device = DpopKey()
    verifier, challenge = pkce_pair()
    redirect = acuarius.app.redirect_uris[0]
    auth = await nav.post(
        AUTHORIZE,
        json={
            "client_id": acuarius.client_id,
            "redirect_uri": redirect,
            "state": "s",
            "code_challenge": challenge,
            "dpop_jkt": device.jkt,
        },
    )
    code = auth.json()["redirect_to"].split("code=")[1].split("&")[0]
    tokens = (
        await client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect,
                "jkt": device.jkt,
            },
            headers=acuarius.basic(),
        )
    ).json()

    info = (
        await client.post(
            INTROSPECT,
            json={"token": tokens["access_token"], "jkt": device.jkt},
            headers=acuarius.basic(),
        )
    ).json()

    assert sorted(info["permissions"]) == sorted(f"acuarius.{t}" for t in TAGS)
    assert [a["slug"] for a in info["applications"]] == ["acuarius"]
    assert set(info["applications"][0]) == {"slug", "name", "base_url"}
    blob = json.dumps(info)
    for foreign in (*FOREIGN, "document"):
        assert foreign not in blob
