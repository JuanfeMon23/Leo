"""Restricciones de `applications`, `app_modules`, `actions`, `roles` y
`role_actions` (incluida la regla rol <-> accion de la misma app)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .conftest import (
    SHA,
    ExpectError,
    make_action,
    make_app,
    make_module,
    make_role,
    unique,
)

UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
FK_VIOLATION = "23503"
NOT_NULL_VIOLATION = "23502"
STRING_TOO_LONG = "22001"

INSERT_APP = (
    "INSERT INTO applications (slug, name, base_url, client_id, "
    "client_secret_hash) VALUES (:slug, 'B', 'http://b', :cid, :sha)"
)
INSERT_ACTION = (
    "INSERT INTO actions (application_id, module_id, verb, tag, name) "
    "VALUES (:app, :mod, :verb, :tag, 'Nombre')"
)
INSERT_ROLE_ACTION = (
    "INSERT INTO role_actions (role_id, action_id, application_id) "
    "VALUES (:role, :action, :app)"
)


async def _app_with_action(conn: AsyncConnection) -> tuple:
    """(app_id, action_id) de una app nueva con una accion `<app>.mod.view`."""
    slug = unique("app")
    app_id = await make_app(conn, slug)
    module_id = await make_module(conn, app_id)
    return app_id, await make_action(conn, app_id, module_id, f"{slug}.mod.view")


# --- applications ---


async def test_slug_y_client_id_de_aplicacion_son_unicos(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    slug = unique("app")
    await make_app(conn, slug)  # client_id = slug
    same_slug = {"slug": slug, "cid": unique("c"), "sha": SHA}
    same_client_id = {"slug": unique("app"), "cid": slug, "sha": SHA}
    assert await expect_error(INSERT_APP, same_slug) == UNIQUE_VIOLATION
    assert await expect_error(INSERT_APP, same_client_id) == UNIQUE_VIOLATION


@pytest.mark.parametrize("secret_hash", ["plain-secret", "A" * 64, "a" * 63])
async def test_client_secret_solo_acepta_hash_sha256_hex(
    expect_error: ExpectError, secret_hash: str
) -> None:
    params = {"slug": unique("app"), "cid": unique("c"), "sha": secret_hash}
    assert await expect_error(INSERT_APP, params) == CHECK_VIOLATION


@pytest.mark.parametrize("slug", ["Leo", "leo_app", "-leo", "leo-", "le.o", ""])
async def test_slug_de_aplicacion_debe_ser_kebab_case(
    expect_error: ExpectError, slug: str
) -> None:
    params = {"slug": slug, "cid": unique("c"), "sha": SHA}
    assert await expect_error(INSERT_APP, params) == CHECK_VIOLATION


# --- app_modules ---


async def test_slug_de_modulo_es_unico_por_app_y_se_repite_entre_apps(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app_a, app_b = await make_app(conn), await make_app(conn)
    await make_module(conn, app_a, "users")
    await make_module(conn, app_b, "users")
    error = await expect_error(
        "INSERT INTO app_modules (application_id, slug, name) "
        "VALUES (:app, 'users', 'Otra')",
        {"app": app_a},
    )
    assert error == UNIQUE_VIOLATION


# --- actions ---


async def test_tag_de_accion_es_unico_globalmente(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app_slug = unique("app")
    app_id = await make_app(conn, app_slug)
    tag = f"{app_slug}.mod.view"
    await make_action(conn, app_id, await make_module(conn, app_id, "mod"), tag)
    other_module = await make_module(conn, app_id, "other")
    params = {"app": app_id, "mod": other_module, "verb": "view", "tag": tag}
    assert await expect_error(INSERT_ACTION, params) == UNIQUE_VIOLATION


@pytest.mark.parametrize(
    "tag",
    [
        "leo.users",  # faltan segmentos
        "leo.users.create.extra",  # sobran segmentos
        "Leo.users.create",  # mayusculas
        "leo.users_admin.create",  # guion bajo
        "leo..create",  # segmento vacio
        "leo.users.-create",  # guion al inicio
        "leo.users.create-",  # guion al final
        "leo.users.cre ate",  # espacio
    ],
)
async def test_tag_de_accion_rechaza_formato_invalido(
    conn: AsyncConnection, expect_error: ExpectError, tag: str
) -> None:
    app_id = await make_app(conn)
    module_id = await make_module(conn, app_id)
    verb = tag.rsplit(".", 1)[-1]
    params = {"app": app_id, "mod": module_id, "verb": verb, "tag": tag}
    assert await expect_error(INSERT_ACTION, params) == CHECK_VIOLATION


@pytest.mark.parametrize("rest", ["users.create", "caja-chica.export-pdf"])
async def test_tag_de_accion_acepta_formato_valido(
    conn: AsyncConnection, rest: str
) -> None:
    app_slug = unique("app")
    app_id = await make_app(conn, app_slug)
    module_id = await make_module(conn, app_id, rest.split(".")[0])
    assert await make_action(conn, app_id, module_id, f"{app_slug}.{rest}")


async def test_tag_debe_terminar_en_el_verbo_de_la_accion(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app_slug = unique("app")
    app_id = await make_app(conn, app_slug)
    module_id = await make_module(conn, app_id)
    params = {
        "app": app_id,
        "mod": module_id,
        "verb": "edit",
        "tag": f"{app_slug}.mod.view",
    }
    assert await expect_error(INSERT_ACTION, params) == CHECK_VIOLATION


async def test_accion_no_puede_colgar_de_un_modulo_de_otra_app(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app_a, app_b = await make_app(conn), await make_app(conn)
    module_of_b = await make_module(conn, app_b)
    params = {
        "app": app_a,
        "mod": module_of_b,
        "verb": "view",
        "tag": f"{unique('x')}.mod.view",
    }
    assert await expect_error(INSERT_ACTION, params) == FK_VIOLATION


INSERT_NAMED_ACTION = (
    "INSERT INTO actions (application_id, module_id, verb, tag, name) "
    "VALUES (:app, :mod, :verb, :tag, :name)"
)


async def test_nombre_de_accion_es_obligatorio(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app_slug = unique("app")
    app_id = await make_app(conn, app_slug)
    module_id = await make_module(conn, app_id)
    error = await expect_error(
        "INSERT INTO actions (application_id, module_id, verb, tag) "
        "VALUES (:app, :mod, 'view', :tag)",
        {"app": app_id, "mod": module_id, "tag": f"{app_slug}.mod.view"},
    )
    assert error == NOT_NULL_VIOLATION


@pytest.mark.parametrize("name", ["", " ", "   "])
async def test_nombre_de_accion_no_puede_estar_en_blanco(
    conn: AsyncConnection, expect_error: ExpectError, name: str
) -> None:
    app_slug = unique("app")
    app_id = await make_app(conn, app_slug)
    module_id = await make_module(conn, app_id)
    params = {
        "app": app_id,
        "mod": module_id,
        "verb": "view",
        "tag": f"{app_slug}.mod.view",
        "name": name,
    }
    assert await expect_error(INSERT_NAMED_ACTION, params) == CHECK_VIOLATION


async def test_nombre_de_accion_tiene_maximo_120_caracteres(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app_slug = unique("app")
    app_id = await make_app(conn, app_slug)
    module_id = await make_module(conn, app_id)
    params = {
        "app": app_id,
        "mod": module_id,
        "verb": "view",
        "tag": f"{app_slug}.mod.view",
        "name": "x" * 121,
    }
    assert await expect_error(INSERT_NAMED_ACTION, params) == STRING_TOO_LONG


async def test_nombre_de_accion_es_unico_por_modulo_y_se_repite_entre_modulos(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app_slug = unique("app")
    app_id = await make_app(conn, app_slug)
    mod_a = await make_module(conn, app_id, "a")
    mod_b = await make_module(conn, app_id, "b")
    await make_action(conn, app_id, mod_a, f"{app_slug}.a.view", name="Consultar")
    # Mismo nombre en otro modulo: permitido.
    await make_action(conn, app_id, mod_b, f"{app_slug}.b.view", name="Consultar")
    params = {
        "app": app_id,
        "mod": mod_a,
        "verb": "edit",
        "tag": f"{app_slug}.a.edit",
        "name": "Consultar",
    }
    assert await expect_error(INSERT_NAMED_ACTION, params) == UNIQUE_VIOLATION


# --- roles y role_actions ---


async def test_slug_de_rol_es_unico_por_app(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app_a, app_b = await make_app(conn), await make_app(conn)
    sql = "INSERT INTO roles (application_id, slug, name) VALUES (:app, 'admin', 'A')"
    await conn.execute(text(sql), {"app": app_a})
    await conn.execute(text(sql), {"app": app_b})
    assert await expect_error(sql, {"app": app_a}) == UNIQUE_VIOLATION


async def test_rol_acepta_acciones_de_su_misma_app(conn: AsyncConnection) -> None:
    app_id, action_id = await _app_with_action(conn)
    role_id = await make_role(conn, app_id)
    params = {"role": role_id, "action": action_id, "app": app_id}
    await conn.execute(text(INSERT_ROLE_ACTION), params)


async def test_rol_rechaza_accion_de_otra_app(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app_a = await make_app(conn)
    app_b, action_of_b = await _app_with_action(conn)
    role_of_a = await make_role(conn, app_a)
    # Se declare la app del rol o la de la accion, siempre falla una FK.
    for app_id in (app_a, app_b):
        params = {"role": role_of_a, "action": action_of_b, "app": app_id}
        assert await expect_error(INSERT_ROLE_ACTION, params) == FK_VIOLATION


async def test_la_misma_accion_no_se_asigna_dos_veces_al_rol(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app_id, action_id = await _app_with_action(conn)
    role_id = await make_role(conn, app_id)
    params = {"role": role_id, "action": action_id, "app": app_id}
    await conn.execute(text(INSERT_ROLE_ACTION), params)
    assert await expect_error(INSERT_ROLE_ACTION, params) == UNIQUE_VIOLATION
