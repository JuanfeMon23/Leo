"""Restricciones de `users` y `user_roles`."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .conftest import ExpectError, make_app, make_role, make_user, unique

UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"

INSERT_USER = (
    "INSERT INTO users (username, email, password_hash, document_type, "
    "document_number, first_name, last_name) VALUES (:username, :email, "
    ":password_hash, :document_type, :document_number, :first_name, 'Gomez')"
)


def _user(**overrides: str) -> dict[str, str]:
    username = unique("user")
    return {
        "username": username,
        "email": f"{username}@example.com",
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
        "document_type": "CC",
        "document_number": unique("DOC").upper(),
        "first_name": "Ana",
        **overrides,
    }


async def test_username_es_unico(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    username = unique("user")
    await make_user(conn, username=username, email=f"{username}@a.com")
    params = _user(username=username)
    assert await expect_error(INSERT_USER, params) == UNIQUE_VIOLATION


async def test_email_es_unico_sin_distinguir_mayusculas(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    email = f"{unique('ana')}@Example.com"
    await make_user(conn, email=email)
    params = _user(email=email.upper())
    assert await expect_error(INSERT_USER, params) == UNIQUE_VIOLATION


async def test_documento_es_unico_por_tipo(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    number = unique("DOC").upper()
    await make_user(conn, document_type="CC", document_number=number)
    # El mismo numero con otro tipo es otra persona: se admite.
    await conn.execute(
        text(INSERT_USER), _user(document_type="CE", document_number=number)
    )
    params = _user(document_type="CC", document_number=number)
    assert await expect_error(INSERT_USER, params) == UNIQUE_VIOLATION


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_type", "XX"),
        ("document_number", "12.345"),
        ("document_number", "abc123"),
        ("username", "Ana"),
        ("username", "ana@leo"),
        ("username", "ab"),
        ("email", "sin-arroba"),
        ("password_hash", "texto-plano"),
        ("password_hash", "$argon2i$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"),
        ("first_name", "   "),
    ],
)
async def test_users_rechaza_valores_invalidos(
    expect_error: ExpectError, field: str, value: str
) -> None:
    assert await expect_error(INSERT_USER, _user(**{field: value})) == CHECK_VIOLATION


async def test_intentos_fallidos_no_pueden_ser_negativos(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    user_id = await make_user(conn)
    error = await expect_error(
        "UPDATE users SET failed_login_attempts = -1 WHERE id = :id", {"id": user_id}
    )
    assert error == CHECK_VIOLATION


async def test_usuario_nuevo_queda_activo_sin_bloqueo(conn: AsyncConnection) -> None:
    user_id = await make_user(conn)
    row = (
        await conn.execute(
            text(
                "SELECT is_active, failed_login_attempts, locked_until "
                "FROM users WHERE id = :id"
            ),
            {"id": user_id},
        )
    ).one()
    assert tuple(row) == (True, 0, None)


async def test_rol_no_se_asigna_dos_veces_al_mismo_usuario(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    user_id = await make_user(conn)
    role_id = await make_role(conn, await make_app(conn))
    sql = "INSERT INTO user_roles (user_id, role_id) VALUES (:user, :role)"
    params = {"user": user_id, "role": role_id}
    await conn.execute(text(sql), params)
    assert await expect_error(sql, params) == UNIQUE_VIOLATION
