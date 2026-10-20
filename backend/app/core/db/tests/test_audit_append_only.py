"""`audit_events` es append-only en la BD: UPDATE, DELETE y TRUNCATE fallan
con el SQLSTATE propio `LEO01`, aunque los ejecute el dueno de la tabla."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.db.triggers import APPEND_ONLY_SQLSTATE

from .conftest import ExpectError, make_app, make_session, make_user

CHECK_VIOLATION = "23514"

INSERT_EVENT = (
    "INSERT INTO audit_events (actor_user_id, actor_username, application_id, "
    "module, action_tag, entity_type, entity_id, changes, result, ip, "
    "session_id) VALUES (:user, 'ana', :app, 'users', :tag, 'user', '42', "
    "CAST(:changes AS jsonb), :result, '10.0.0.1', :session)"
)


@pytest.fixture
async def event_params(conn: AsyncConnection) -> dict:
    user_id = await make_user(conn)
    return {
        "user": user_id,
        "app": await make_app(conn),
        "session": await make_session(conn, user_id),
        "tag": "leo.users.edit",
        "changes": '{"email": {"before": "a@x.com", "after": "b@x.com"}}',
        "result": "ok",
    }


async def _insert_event(conn: AsyncConnection, params: dict) -> object:
    return (
        await conn.execute(text(INSERT_EVENT + " RETURNING id"), params)
    ).scalar_one()


async def test_insertar_evento_funciona_y_fija_occurred_at(
    conn: AsyncConnection, event_params: dict
) -> None:
    event_id = await _insert_event(conn, event_params)
    row = (
        await conn.execute(
            text(
                "SELECT occurred_at IS NOT NULL, changes -> 'email' ->> 'after' "
                "FROM audit_events WHERE id = :id"
            ),
            {"id": event_id},
        )
    ).one()
    assert tuple(row) == (True, "b@x.com")


async def test_update_de_evento_falla_con_sqlstate_propio(
    conn: AsyncConnection, event_params: dict, expect_error: ExpectError
) -> None:
    event_id = await _insert_event(conn, event_params)
    error = await expect_error(
        "UPDATE audit_events SET result = 'denied' WHERE id = :id", {"id": event_id}
    )
    assert error == APPEND_ONLY_SQLSTATE


async def test_delete_de_evento_falla_con_sqlstate_propio(
    conn: AsyncConnection, event_params: dict, expect_error: ExpectError
) -> None:
    event_id = await _insert_event(conn, event_params)
    error = await expect_error(
        "DELETE FROM audit_events WHERE id = :id", {"id": event_id}
    )
    assert error == APPEND_ONLY_SQLSTATE


async def test_truncate_de_auditoria_falla_con_sqlstate_propio(
    conn: AsyncConnection, event_params: dict, expect_error: ExpectError
) -> None:
    await _insert_event(conn, event_params)
    assert await expect_error("TRUNCATE audit_events") == APPEND_ONLY_SQLSTATE


async def test_el_evento_sigue_intacto_tras_intentos_de_modificarlo(
    conn: AsyncConnection, event_params: dict, expect_error: ExpectError
) -> None:
    event_id = await _insert_event(conn, event_params)
    await expect_error("DELETE FROM audit_events WHERE id = :id", {"id": event_id})
    remaining = (
        await conn.execute(
            text("SELECT result FROM audit_events WHERE id = :id"), {"id": event_id}
        )
    ).scalar_one()
    assert remaining == "ok"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tag", "no-es-un-tag"),
        ("result", "maybe"),
        ("changes", '["no", "objeto"]'),
    ],
)
async def test_evento_rechaza_valores_invalidos(
    event_params: dict, expect_error: ExpectError, field: str, value: str
) -> None:
    params = {**event_params, field: value}
    assert await expect_error(INSERT_EVENT, params) == CHECK_VIOLATION
