"""Credenciales de servicio: `service_grants` (una app llamadora recibe un rol
de OTRA app) y `service_tokens` (tokens de maquina opacos, solo hash, vida
maxima de 1 hora, sin sesion ni usuario)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .conftest import ExpectError, make_app, make_role, random_sha

UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
FK_VIOLATION = "23503"
NOT_NULL_VIOLATION = "23502"
STRING_TOO_LONG = "22001"

INSERT_GRANT = (
    "INSERT INTO service_grants (caller_application_id, role_id, application_id) "
    "VALUES (:caller, :role, :target)"
)
INSERT_TOKEN = (
    "INSERT INTO service_tokens (token_hash, caller_application_id, "
    "audience_application_id, expires_at) "
    "VALUES (:hash, :caller, :audience, now() + interval '15 minutes')"
)


@pytest.fixture
async def ctx(conn: AsyncConnection) -> dict:
    """Llamadora, destino y un rol del destino."""
    target = await make_app(conn)
    return {
        "caller": await make_app(conn),
        "target": target,
        "role": await make_role(conn, target),
    }


def _grant(ctx: dict, **overrides: object) -> dict:
    return {
        "caller": ctx["caller"],
        "role": ctx["role"],
        "target": ctx["target"],
        **overrides,
    }


def _token(ctx: dict, **overrides: object) -> dict:
    return {
        "hash": random_sha(),
        "caller": ctx["caller"],
        "audience": ctx["target"],
        **overrides,
    }


# --- service_grants ---


async def test_concesion_valida_se_inserta_con_id_y_timestamps(
    conn: AsyncConnection, ctx: dict
) -> None:
    row = (
        await conn.execute(
            text(
                INSERT_GRANT + " RETURNING id, created_at IS NOT NULL, "
                "updated_at IS NOT NULL"
            ),
            _grant(ctx),
        )
    ).one()
    assert row.id is not None
    assert (row[1], row[2]) == (True, True)


async def test_concesion_es_unica_por_llamadora_y_rol(
    conn: AsyncConnection, ctx: dict, expect_error: ExpectError
) -> None:
    await conn.execute(text(INSERT_GRANT), _grant(ctx))
    assert await expect_error(INSERT_GRANT, _grant(ctx)) == UNIQUE_VIOLATION


async def test_una_app_no_se_concede_acceso_a_si_misma(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    app = await make_app(conn)
    role = await make_role(conn, app)
    error = await expect_error(
        INSERT_GRANT, {"caller": app, "role": role, "target": app}
    )
    assert error == CHECK_VIOLATION


async def test_rol_de_otra_app_que_no_es_la_destino_se_rechaza(
    conn: AsyncConnection, ctx: dict, expect_error: ExpectError
) -> None:
    other = await make_app(conn)
    # El rol es de `target`, pero la fila dice que el destino es `other`.
    assert await expect_error(INSERT_GRANT, _grant(ctx, target=other)) == FK_VIOLATION


async def test_llamadora_debe_existir(ctx: dict, expect_error: ExpectError) -> None:
    error = await expect_error(
        INSERT_GRANT, _grant(ctx, caller="0199f000-0000-7000-8000-000000000000")
    )
    assert error == FK_VIOLATION


async def test_concesion_se_borra_sin_desactivar(
    conn: AsyncConnection, ctx: dict
) -> None:
    grant_id = (
        await conn.execute(text(INSERT_GRANT + " RETURNING id"), _grant(ctx))
    ).scalar_one()
    await conn.execute(
        text("DELETE FROM service_grants WHERE id = :id"), {"id": grant_id}
    )
    left = (
        await conn.execute(
            text("SELECT count(*) FROM service_grants WHERE id = :id"), {"id": grant_id}
        )
    ).scalar_one()
    assert left == 0


async def test_no_se_puede_borrar_un_rol_con_concesiones(
    conn: AsyncConnection, ctx: dict, expect_error: ExpectError
) -> None:
    await conn.execute(text(INSERT_GRANT), _grant(ctx))
    error = await expect_error("DELETE FROM roles WHERE id = :id", {"id": ctx["role"]})
    assert error == FK_VIOLATION


# --- service_tokens ---


async def test_token_de_servicio_valido_no_lleva_sesion_ni_usuario(
    conn: AsyncConnection, ctx: dict
) -> None:
    await conn.execute(text(INSERT_TOKEN), _token(ctx))
    columns = {
        r[0]
        for r in await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'service_tokens'"
            )
        )
    }
    assert columns == {
        "id",
        "token_hash",
        "caller_application_id",
        "audience_application_id",
        "expires_at",
        "revoked_at",
        "created_at",
        "updated_at",
    }


async def test_token_de_servicio_hash_es_unico(
    conn: AsyncConnection, ctx: dict, expect_error: ExpectError
) -> None:
    params = _token(ctx)
    await conn.execute(text(INSERT_TOKEN), params)
    assert await expect_error(INSERT_TOKEN, params) == UNIQUE_VIOLATION


@pytest.mark.parametrize("token_hash", ["token-en-claro", "F" * 64, "a" * 65])
async def test_token_de_servicio_solo_guarda_hash_sha256_hex(
    ctx: dict, expect_error: ExpectError, token_hash: str
) -> None:
    error = await expect_error(INSERT_TOKEN, _token(ctx, hash=token_hash))
    assert error in (CHECK_VIOLATION, STRING_TOO_LONG)


async def test_token_de_servicio_exige_llamadora_y_audiencia(
    ctx: dict, expect_error: ExpectError
) -> None:
    assert (
        await expect_error(INSERT_TOKEN, _token(ctx, caller=None)) == NOT_NULL_VIOLATION
    )
    assert (
        await expect_error(INSERT_TOKEN, _token(ctx, audience=None))
        == NOT_NULL_VIOLATION
    )


async def test_token_de_servicio_apps_deben_existir(
    ctx: dict, expect_error: ExpectError
) -> None:
    ghost = "0199f000-0000-7000-8000-000000000000"
    assert await expect_error(INSERT_TOKEN, _token(ctx, caller=ghost)) == FK_VIOLATION
    assert await expect_error(INSERT_TOKEN, _token(ctx, audience=ghost)) == FK_VIOLATION


@pytest.mark.parametrize(
    ("expires", "expected"),
    [
        ("now() - interval '1 minute'", CHECK_VIOLATION),
        ("now() + interval '1 hour 1 minute'", CHECK_VIOLATION),
        ("now() + interval '2 hours'", CHECK_VIOLATION),
        ("now() + interval '59 minutes'", None),
    ],
)
async def test_token_de_servicio_vive_como_maximo_una_hora(
    ctx: dict, expect_error: ExpectError, expires: str, expected: str | None
) -> None:
    sql = INSERT_TOKEN.replace("now() + interval '15 minutes'", expires)
    assert await expect_error(sql, _token(ctx)) == expected


async def test_token_de_servicio_no_se_puede_alargar_mas_alla_de_una_hora(
    conn: AsyncConnection, ctx: dict, expect_error: ExpectError
) -> None:
    token_id = (
        await conn.execute(text(INSERT_TOKEN + " RETURNING id"), _token(ctx))
    ).scalar_one()
    error = await expect_error(
        "UPDATE service_tokens SET expires_at = created_at + interval '2 hours' "
        "WHERE id = :id",
        {"id": token_id},
    )
    assert error == CHECK_VIOLATION


async def test_token_de_servicio_se_revoca_con_revoked_at(
    conn: AsyncConnection, ctx: dict
) -> None:
    token_id = (
        await conn.execute(text(INSERT_TOKEN + " RETURNING id"), _token(ctx))
    ).scalar_one()
    revoked = (
        await conn.execute(
            text(
                "UPDATE service_tokens SET revoked_at = now() WHERE id = :id "
                "RETURNING revoked_at"
            ),
            {"id": token_id},
        )
    ).scalar_one()
    assert revoked is not None


async def test_indices_de_service_tokens_y_service_grants(
    conn: AsyncConnection,
) -> None:
    rows = await conn.execute(
        text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
            "AND tablename IN ('service_tokens', 'service_grants')"
        )
    )
    defs = {name: definition for name, definition in rows}
    assert any("UNIQUE" in d and "(token_hash)" in d for d in defs.values()), defs
    assert any(
        "(caller_application_id, audience_application_id)" in d for d in defs.values()
    ), defs
    assert any(
        "UNIQUE" in d and "(caller_application_id, role_id)" in d for d in defs.values()
    ), defs
