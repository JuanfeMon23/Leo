"""Catalogo de tipos de documento: lectura (usuarios y servicios), gestion con
permisos `leo.document-types.*` y validacion contra la BD en usuarios y
pacientes."""

import pytest
from sqlalchemy import select

from app.conftest import login_as
from app.core.db.seeds.catalog import LEO_PROVISIONER_ROLE_SLUG
from app.core.db.seeds.leo_app import seed_leo_provisioner_role
from app.modules.audit.models import AuditEvent
from app.modules.roles.models import Role
from app.modules.users import controller
from app.modules.users.models import DocumentType
from app.testkit import (
    STRONG_PASSWORD,
    grant,
    grant_service_access,
    leo_app,
    make_client_app,
    make_role,
    make_user,
    unique,
)

DOCUMENT_TYPES = "/api/v1/document-types"
USERS = "/api/v1/users"
PATIENTS = "/api/v1/users/service/patients"
TOKEN = "/api/v1/auth/token"
SEED_CODES = ["CC", "CE", "TI", "RC", "PA", "NIT", "PEP", "PPT"]


def new_code() -> str:
    return "T" + unique("")[-6:].replace("-", "").upper()[:6]


def user_body(**overrides):
    suffix = unique("u").replace("-", "")
    data = {
        "username": f"usr{suffix}",
        "email": f"usr{suffix}@example.com",
        "password": STRONG_PASSWORD,
        "document_type": "CC",
        "document_number": suffix.upper(),
        "first_name": "Laura",
        "last_name": "Pérez",
    }
    data.update(overrides)
    return data


async def deactivate_in_db(session, code: str) -> None:
    row = (
        await session.scalars(select(DocumentType).where(DocumentType.code == code))
    ).one()
    row.is_active = False
    await session.commit()


@pytest.fixture(autouse=True)
def _reset_limiter():
    controller._provision_limiter = None
    yield
    controller._provision_limiter = None


@pytest.fixture
async def service_headers(session, client):
    """Bearer de una app con el rol aprovisionador (acceso de servicio a Leo)."""
    leo = await leo_app(session)
    conn = await session.connection()
    await conn.run_sync(lambda sync: seed_leo_provisioner_role(sync, leo.id))
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
    response = await client.post(
        TOKEN,
        json={"grant_type": "client_credentials", "audience": "leo"},
        headers=caller.basic(),
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# --- Lectura ---------------------------------------------------------------


async def test_usuario_autenticado_lista_activos_ordenados(admin):
    response = await admin.get(DOCUMENT_TYPES)

    assert response.status_code == 200, response.text
    items = response.json()
    assert [item["code"] for item in items] == SEED_CODES
    assert items[0] == {
        "code": "CC",
        "name": "Cédula de ciudadanía",
        "sort_order": 10,
        "is_active": True,
    }
    assert [item["sort_order"] for item in items] == sorted(
        item["sort_order"] for item in items
    )


async def test_usuario_sin_permisos_leo_tambien_puede_leer(session, make_browser):
    plain = await login_as(session, make_browser, await make_user(session))

    response = await plain.get(DOCUMENT_TYPES)

    assert response.status_code == 200


async def test_lectura_sin_credenciales_devuelve_401(client):
    response = await client.get(DOCUMENT_TYPES)

    assert response.status_code == 401


async def test_servicio_con_bearer_valido_puede_leer(client, service_headers):
    response = await client.get(DOCUMENT_TYPES, headers=service_headers)

    assert response.status_code == 200, response.text
    assert [item["code"] for item in response.json()] == SEED_CODES


async def test_bearer_invalido_devuelve_401_invalid_token(client):
    response = await client.get(
        DOCUMENT_TYPES, headers={"Authorization": "Bearer no-existe"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


async def test_filtro_active_false_lista_solo_inactivos(admin, session):
    await deactivate_in_db(session, "RC")

    default = await admin.get(DOCUMENT_TYPES)
    inactive = await admin.get(f"{DOCUMENT_TYPES}?active=false")

    assert "RC" not in [item["code"] for item in default.json()]
    assert [item["code"] for item in inactive.json()] == ["RC"]


# --- Gestion ---------------------------------------------------------------


async def test_crear_tipo_de_documento(admin, session):
    code = new_code()

    response = await admin.post(
        DOCUMENT_TYPES, json={"code": code.lower(), "name": "Nuevo", "sort_order": 90}
    )

    assert response.status_code == 201, response.text
    assert response.json() == {
        "code": code,
        "name": "Nuevo",
        "sort_order": 90,
        "is_active": True,
    }
    audited = await session.scalars(
        select(AuditEvent).where(
            AuditEvent.action_tag == "leo.document-types.create",
            AuditEvent.result == "ok",
        )
    )
    assert len(list(audited)) == 1
    listed = await admin.get(DOCUMENT_TYPES)
    assert listed.json()[-1]["code"] == code


async def test_crear_con_codigo_duplicado_devuelve_409(admin):
    response = await admin.post(DOCUMENT_TYPES, json={"code": "CC", "name": "Otra"})

    assert response.status_code == 409
    assert response.json()["code"] == "duplicate"


@pytest.mark.parametrize("code", ["1AB", "A-B", "ABCDEFGHI", ""])
async def test_crear_con_codigo_invalido_devuelve_422(admin, code):
    response = await admin.post(DOCUMENT_TYPES, json={"code": code, "name": "X"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_editar_nombre_y_orden(admin):
    response = await admin.patch(
        f"{DOCUMENT_TYPES}/PA", json={"name": "Pasaporte nacional", "sort_order": 5}
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Pasaporte nacional"
    assert response.json()["sort_order"] == 5
    listed = await admin.get(DOCUMENT_TYPES)
    assert listed.json()[0]["code"] == "PA"


async def test_editar_no_permite_cambiar_codigo_ni_estado(admin):
    for field, value in (("code", "XX"), ("is_active", False)):
        response = await admin.patch(f"{DOCUMENT_TYPES}/PA", json={field: value})
        assert response.status_code == 422, field


async def test_editar_inexistente_devuelve_404(admin):
    response = await admin.patch(f"{DOCUMENT_TYPES}/ZZZ", json={"name": "X"})

    assert response.status_code == 404


async def test_desactivar_y_reactivar(admin):
    off = await admin.post(f"{DOCUMENT_TYPES}/PEP/deactivate")
    listed_off = await admin.get(DOCUMENT_TYPES)
    on = await admin.post(f"{DOCUMENT_TYPES}/PEP/activate")
    listed_on = await admin.get(DOCUMENT_TYPES)

    assert off.status_code == 200 and off.json()["is_active"] is False
    assert "PEP" not in [item["code"] for item in listed_off.json()]
    assert on.status_code == 200 and on.json()["is_active"] is True
    assert "PEP" in [item["code"] for item in listed_on.json()]


async def test_no_existe_borrado(admin):
    response = await admin.delete(f"{DOCUMENT_TYPES}/CC")

    assert response.status_code == 405


async def test_gestion_sin_permiso_devuelve_403_y_deja_evento_denied(
    session, make_browser
):
    plain = await login_as(session, make_browser, await make_user(session))

    attempts = [
        await plain.post(DOCUMENT_TYPES, json={"code": new_code(), "name": "X"}),
        await plain.patch(f"{DOCUMENT_TYPES}/CC", json={"name": "X"}),
        await plain.post(f"{DOCUMENT_TYPES}/CC/deactivate"),
        await plain.post(f"{DOCUMENT_TYPES}/CC/activate"),
    ]

    assert [response.status_code for response in attempts] == [403] * 4
    denied = await session.scalars(
        select(AuditEvent).where(
            AuditEvent.action_tag.like("leo.document-types.%"),
            AuditEvent.result == "denied",
        )
    )
    assert len(list(denied)) == 4


async def test_servicio_no_puede_gestionar_el_catalogo(client, service_headers):
    response = await client.post(
        DOCUMENT_TYPES, json={"code": new_code(), "name": "X"}, headers=service_headers
    )

    assert response.status_code in (401, 403)


async def test_permiso_granular_edit_no_permite_desactivar(session, make_browser):
    leo = await leo_app(session)
    role = await make_role(session, leo.id, ["leo.document-types.edit"])
    user = await make_user(session)
    await grant(session, user, role)
    editor = await login_as(session, make_browser, user)

    edited = await editor.patch(f"{DOCUMENT_TYPES}/CC", json={"name": "Cédula"})
    deactivated = await editor.post(f"{DOCUMENT_TYPES}/CC/deactivate")

    assert edited.status_code == 200, edited.text
    assert deactivated.status_code == 403


# --- Validacion en usuarios y pacientes ------------------------------------


async def test_crear_usuario_con_tipo_inexistente_devuelve_422(admin):
    response = await admin.post(USERS, json=user_body(document_type="ZZ"))

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_document_type"
    assert body["details"] == {"document_type": "ZZ"}


async def test_crear_usuario_con_tipo_inactivo_devuelve_422(admin, session):
    await deactivate_in_db(session, "TI")

    response = await admin.post(USERS, json=user_body(document_type="TI"))

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_document_type"


async def test_crear_usuario_normaliza_a_mayusculas_y_acepta_tipo_nuevo(admin):
    code = new_code()
    await admin.post(DOCUMENT_TYPES, json={"code": code, "name": "Nuevo"})

    response = await admin.post(USERS, json=user_body(document_type=code.lower()))

    assert response.status_code == 201, response.text
    assert response.json()["document_type"] == code


async def test_editar_usuario_con_tipo_inactivo_devuelve_422(admin, session):
    created = await admin.post(USERS, json=user_body())
    await deactivate_in_db(session, "CE")

    response = await admin.patch(
        f"{USERS}/{created.json()['id']}", json={"document_type": "CE"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_document_type"


async def test_editar_usuario_sin_tocar_el_tipo_no_revalida_un_tipo_ya_inactivo(
    admin, session
):
    created = await admin.post(USERS, json=user_body(document_type="NIT"))
    await deactivate_in_db(session, "NIT")

    response = await admin.patch(
        f"{USERS}/{created.json()['id']}", json={"first_name": "Marta"}
    )

    assert response.status_code == 200, response.text


async def test_aprovisionar_paciente_con_tipo_inactivo_devuelve_422(
    client, session, service_headers
):
    from app.core.db.seeds.acuarius_app import seed_acuarius_application

    conn = await session.connection()
    await conn.run_sync(seed_acuarius_application)
    await deactivate_in_db(session, "PPT")

    response = await client.post(
        PATIENTS, json=user_body(document_type="PPT"), headers=service_headers
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_document_type"
