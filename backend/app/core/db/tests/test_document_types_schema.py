"""Catalogo `document_types` y su FK desde `users.document_type`."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.db.seeds.catalog import DOCUMENT_TYPES
from app.core.db.seeds.document_types import seed_document_types

from .conftest import ExpectError, alembic, make_user, unique

UNIQUE_VIOLATION = "23505"
FK_VIOLATION = "23503"
CHECK_VIOLATION = "23514"

INSERT_TYPE = "INSERT INTO document_types (code, name) VALUES (:code, :name)"
INSERT_USER = (
    "INSERT INTO users (username, email, password_hash, document_type, "
    "document_number, first_name, last_name) VALUES (:u, :e, "
    "'$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA', :t, :n, 'Ana', 'Gomez')"
)


def _code() -> str:
    return "Z" + uuid4().hex[:6].upper()


async def test_migracion_siembra_los_ocho_codigos_vigentes(
    conn: AsyncConnection,
) -> None:
    rows = await conn.execute(
        text("SELECT code, name, sort_order FROM document_types ORDER BY sort_order")
    )
    assert [tuple(row) for row in rows] == list(DOCUMENT_TYPES)
    assert [row[0] for row in DOCUMENT_TYPES] == [
        "CC", "CE", "TI", "RC", "PA", "NIT", "PEP", "PPT"
    ]  # fmt: skip


async def test_tipo_nuevo_queda_activo_con_orden_cero(conn: AsyncConnection) -> None:
    code = _code()
    await conn.execute(text(INSERT_TYPE), {"code": code, "name": "Nuevo"})
    row = (
        await conn.execute(
            text("SELECT is_active, sort_order FROM document_types WHERE code = :c"),
            {"c": code},
        )
    ).one()
    assert tuple(row) == (True, 0)


async def test_code_es_unico(conn: AsyncConnection, expect_error: ExpectError) -> None:
    assert (
        await expect_error(INSERT_TYPE, {"code": "CC", "name": "Otra"})
        == UNIQUE_VIOLATION
    )


@pytest.mark.parametrize(
    ("code", "name"),
    [("cc2", "Minuscula"), ("1AB", "Empieza por digito"), ("A-B", "Guion"),
     ("OK", "   ")],
)  # fmt: skip
async def test_rechaza_code_o_nombre_invalidos(
    expect_error: ExpectError, code: str, name: str
) -> None:
    assert await expect_error(INSERT_TYPE, {"code": code, "name": name}) == (
        CHECK_VIOLATION
    )


async def test_sort_order_no_puede_ser_negativo(expect_error: ExpectError) -> None:
    sql = "INSERT INTO document_types (code, name, sort_order) VALUES ('NEG', 'x', -1)"
    assert await expect_error(sql) == CHECK_VIOLATION


async def test_usuario_con_tipo_inexistente_viola_la_fk(
    expect_error: ExpectError,
) -> None:
    params = {
        "u": unique("user"),
        "e": f"{unique('e')}@example.com",
        "t": "XX",
        "n": unique("N").upper(),
    }
    assert await expect_error(INSERT_USER, params) == FK_VIOLATION


async def test_usuario_acepta_un_tipo_agregado_al_catalogo(
    conn: AsyncConnection,
) -> None:
    code = _code()
    await conn.execute(text(INSERT_TYPE), {"code": code, "name": "Nuevo"})
    await make_user(conn, document_type=code)


async def test_tipo_referenciado_no_se_borra(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    await make_user(conn, document_type="TI")
    assert (
        await expect_error("DELETE FROM document_types WHERE code = 'TI'")
        == FK_VIOLATION
    )
    assert (
        await expect_error("UPDATE document_types SET code = 'TX' WHERE code = 'TI'")
        == FK_VIOLATION
    )


async def test_semilla_es_idempotente_y_no_pisa_ediciones(
    conn: AsyncConnection,
) -> None:
    await conn.execute(
        text(
            "UPDATE document_types SET name = 'Editado', is_active = false, "
            "sort_order = 99 WHERE code = 'PA'"
        )
    )
    await conn.run_sync(seed_document_types)
    await conn.run_sync(seed_document_types)
    count = (
        await conn.execute(text("SELECT count(*) FROM document_types"))
    ).scalar_one()
    row = (
        await conn.execute(
            text(
                "SELECT name, is_active, sort_order FROM document_types WHERE code='PA'"
            )
        )
    ).one()
    assert count == len(DOCUMENT_TYPES)
    assert tuple(row) == ("Editado", False, 99)


async def test_0009_baja_y_sube_con_usuarios_existentes(engine: AsyncEngine) -> None:
    """Downgrade restaura el CHECK sin tocar usuarios; con un codigo fuera de los
    8 originales aborta con mensaje claro; volver a subir deja el catalogo."""
    number = unique("D").upper()
    code = _code()
    async with engine.begin() as connection:
        await connection.execute(text(INSERT_TYPE), {"code": code, "name": "Extra"})
        await make_user(connection, document_type="CE", document_number=number)
        custom = await make_user(connection, document_type=code)
    try:
        with pytest.raises(AssertionError, match="fuera de"):
            alembic("downgrade", "0008")
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": custom}
            )
    try:
        alembic("downgrade", "0008")
        async with engine.connect() as connection:
            tables = (
                await connection.execute(
                    text("SELECT to_regclass('public.document_types')")
                )
            ).scalar_one()
            check = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname = 'ck_users_document_type'"
                    )
                )
            ).scalar_one()
            kept = (
                await connection.execute(
                    text("SELECT document_type FROM users WHERE document_number = :n"),
                    {"n": number},
                )
            ).scalar_one()
        assert (tables, check, kept) == (None, 1, "CE")
    finally:
        alembic("upgrade", "head")
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM users WHERE document_number = :n"), {"n": number}
            )
            await connection.execute(
                text("DELETE FROM document_types WHERE code = :c"), {"c": code}
            )
