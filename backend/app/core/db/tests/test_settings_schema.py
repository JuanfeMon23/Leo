"""`settings` (CHECK de clave, tipo y rango) y `settings_history`
(append-only con SQLSTATE `LEO01`)."""

import json
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.db.triggers import APPEND_ONLY_SQLSTATE

from .conftest import ExpectError, make_user

CHECK_VIOLATION = "23514"
FK_VIOLATION = "23503"
NO_USER = "00000000-0000-0000-0000-000000000000"

INSERT_SETTING = (
    "INSERT INTO settings (key, value, value_type, min_value, max_value, "
    "default_value, unit, group_name, description) VALUES (:key, "
    "CAST(:value AS jsonb), :vt, CAST(:min AS jsonb), CAST(:max AS jsonb), "
    "CAST(:default AS jsonb), :unit, 'sesiones', 'Descripcion')"
)
INSERT_HISTORY = (
    "INSERT INTO settings_history (setting_key, old_value, new_value, "
    "version_after, changed_by, changed_by_username, reason, request_id) "
    "VALUES (:key, CAST(:old AS jsonb), CAST(:new AS jsonb), :version, :user, "
    "'ana', :reason, 'req-1')"
)


def setting(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "key": "sessions.idle_timeout",
        "value": "30",
        "vt": "int",
        "min": "5",
        "max": "120",
        "default": "30",
        "unit": "minutes",
    }
    return {**params, **overrides}


def j(value: Any) -> str:
    return json.dumps(value)


async def test_insertar_ajuste_valido_aplica_defaults(conn: AsyncConnection) -> None:
    await conn.execute(text(INSERT_SETTING), setting())
    row = (
        await conn.execute(
            text(
                "SELECT version, requires_security_permission, "
                "updated_at IS NOT NULL, created_at IS NOT NULL, updated_by "
                "FROM settings WHERE key = 'sessions.idle_timeout'"
            )
        )
    ).one()
    assert tuple(row) == (1, False, True, True, None)


@pytest.mark.parametrize(
    "key",
    ["sinpunto", "Mayus.cula", "a.b-c", "a..b", ".a.b", "a.b.", "a. b", "a.b/c"],
)
async def test_clave_invalida_se_rechaza(expect_error: ExpectError, key: str) -> None:
    assert await expect_error(INSERT_SETTING, setting(key=key)) == CHECK_VIOLATION


@pytest.mark.parametrize("key", ["a.b", "sessions.max_per_user", "x1.y_2.z3"])
async def test_clave_valida_se_acepta(expect_error: ExpectError, key: str) -> None:
    assert await expect_error(INSERT_SETTING, setting(key=key)) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"vt": "decimal"},
        {"value": j("treinta")},  # int con string
        {"value": "30.5"},  # int con decimal
        {"default": "true"},
        {"min": j("5")},
        {"vt": "float", "value": "true", "min": None, "max": None},
        {"vt": "bool", "value": "1", "min": None, "max": None, "default": "true"},
        {"vt": "bool", "value": "true", "default": "true"},  # bool con min/max
        {"vt": "str", "value": "5", "min": None, "max": None, "default": j("x")},
        {"vt": "str", "value": j("x"), "default": j("x")},  # str con min/max
        {"value": "null"},
    ],
)
async def test_tipo_incoherente_se_rechaza(
    expect_error: ExpectError, overrides: dict
) -> None:
    assert await expect_error(INSERT_SETTING, setting(**overrides)) == CHECK_VIOLATION


@pytest.mark.parametrize(
    "overrides",
    [
        {"value": "4"},  # < min
        {"value": "121"},  # > max
        {"default": "4"},
        {"default": "500"},
        {"min": "200", "max": "100", "value": "150", "default": "150"},
        {"vt": "float", "value": "0.4", "min": "0.5", "max": "1.5", "default": "1"},
        {"vt": "float", "value": "1", "min": "0.5", "max": "1.5", "default": "1.6"},
    ],
)
async def test_fuera_de_rango_se_rechaza(
    expect_error: ExpectError, overrides: dict
) -> None:
    assert await expect_error(INSERT_SETTING, setting(**overrides)) == CHECK_VIOLATION


@pytest.mark.parametrize(
    "overrides",
    [
        {"value": "5"},
        {"value": "120"},
        {"min": None, "value": "-3", "default": "0"},
        {"max": None, "value": "100000"},
        {"min": None, "max": None},
        {"vt": "float", "value": "0.75", "min": "0.5", "max": "1.5", "default": "1.5"},
        {
            "vt": "bool",
            "value": "false",
            "min": None,
            "max": None,
            "default": "true",
            "unit": None,
        },
        {
            "vt": "str",
            "value": j("a"),
            "min": None,
            "max": None,
            "default": j("b"),
            "unit": None,
        },
    ],
)
async def test_valores_validos_en_el_borde_se_aceptan(
    expect_error: ExpectError, overrides: dict
) -> None:
    assert await expect_error(INSERT_SETTING, setting(**overrides)) is None


async def test_update_invalido_se_rechaza(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    await conn.execute(text(INSERT_SETTING), setting())
    key = {"k": "sessions.idle_timeout"}
    assert (
        await expect_error("UPDATE settings SET value = '999'::jsonb WHERE key = :k", key)
        == CHECK_VIOLATION
    )
    assert (
        await expect_error("UPDATE settings SET version = 0 WHERE key = :k", key)
        == CHECK_VIOLATION
    )


async def test_updated_by_exige_usuario_existente(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    await conn.execute(text(INSERT_SETTING), setting())
    user_id = await make_user(conn)
    sql = "UPDATE settings SET updated_by = :u WHERE key = 'sessions.idle_timeout'"
    assert await expect_error(sql, {"u": user_id}) is None
    assert await expect_error(sql, {"u": NO_USER}) == FK_VIOLATION


# --- settings_history -------------------------------------------------------


def history(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "key": "sessions.idle_timeout",
        "old": "30",
        "new": "45",
        "version": 2,
        "user": None,
        "reason": "ajuste de politica",
    }
    return {**params, **overrides}


async def _insert_history(conn: AsyncConnection, **overrides: Any) -> object:
    return (
        await conn.execute(text(INSERT_HISTORY + " RETURNING id"), history(**overrides))
    ).scalar_one()


async def test_historial_inserta_sin_fk_al_catalogo(conn: AsyncConnection) -> None:
    # La clave no existe en `settings`: el historial sobrevive al catalogo.
    row_id = await _insert_history(conn, key="clave.retirada")
    row = (
        await conn.execute(
            text(
                "SELECT old_value, new_value, changed_at IS NOT NULL, request_id "
                "FROM settings_history WHERE id = :id"
            ),
            {"id": row_id},
        )
    ).one()
    assert tuple(row) == (30, 45, True, "req-1")


async def test_historial_con_usuario_exige_que_exista(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    await _insert_history(conn, user=await make_user(conn))
    assert await expect_error(INSERT_HISTORY, history(user=NO_USER)) == FK_VIOLATION


@pytest.mark.parametrize(
    ("overrides", "sqlstate"),
    [
        ({"reason": "ab"}, CHECK_VIOLATION),
        ({"reason": ""}, CHECK_VIOLATION),
        ({"version": 0}, CHECK_VIOLATION),
        ({"reason": "x" * 501}, "22001"),  # excede varchar(500)
    ],
)
async def test_historial_rechaza_valores_invalidos(
    expect_error: ExpectError, overrides: dict, sqlstate: str
) -> None:
    assert await expect_error(INSERT_HISTORY, history(**overrides)) == sqlstate


async def test_historial_update_falla_con_sqlstate_propio(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    row_id = await _insert_history(conn)
    error = await expect_error(
        "UPDATE settings_history SET reason = 'cambiado' WHERE id = :id",
        {"id": row_id},
    )
    assert error == APPEND_ONLY_SQLSTATE


async def test_historial_delete_falla_con_sqlstate_propio(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    row_id = await _insert_history(conn)
    error = await expect_error(
        "DELETE FROM settings_history WHERE id = :id", {"id": row_id}
    )
    assert error == APPEND_ONLY_SQLSTATE


async def test_historial_truncate_falla_con_sqlstate_propio(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    await _insert_history(conn)
    assert await expect_error("TRUNCATE settings_history") == APPEND_ONLY_SQLSTATE


async def test_historial_intacto_tras_intentos_de_modificarlo(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    row_id = await _insert_history(conn)
    await expect_error("DELETE FROM settings_history WHERE id = :id", {"id": row_id})
    await expect_error(
        "UPDATE settings_history SET new_value = '1'::jsonb WHERE id = :id",
        {"id": row_id},
    )
    new_value = (
        await conn.execute(
            text("SELECT new_value FROM settings_history WHERE id = :id"),
            {"id": row_id},
        )
    ).scalar_one()
    assert new_value == 45
