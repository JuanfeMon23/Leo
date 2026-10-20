"""Restricciones de `sessions`, `tokens` y `authorization_codes`: solo
hashes, atadura al `jkt`, familia de refresh y code de 60 s, PKCE S256."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .conftest import (
    JKT,
    SHA,
    ExpectError,
    make_app,
    make_session,
    make_user,
    random_sha,
)

UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
STRING_TOO_LONG = "22001"  # excede el varchar

INSERT_SESSION = (
    "INSERT INTO sessions (user_id, jkt, secret_hash, expires_at) "
    "VALUES (:user, :jkt, :secret, now() + interval '1 hour')"
)
INSERT_TOKEN = (
    "INSERT INTO tokens (token_hash, token_type, session_id, application_id, "
    "jkt, family_id, expires_at) VALUES (:hash, :type, :session, :app, :jkt, "
    ":family, now() + interval '15 minutes')"
)
INSERT_CODE = (
    "INSERT INTO authorization_codes (code_hash, application_id, session_id, "
    "redirect_uri, code_challenge, code_challenge_method, dpop_jkt) VALUES "
    "(:hash, :app, :session, 'http://app/cb', :challenge, :method, :jkt)"
)


@pytest.fixture
async def ctx(conn: AsyncConnection) -> dict:
    """App + sesion de un usuario, base de tokens y codes."""
    session_id = await make_session(conn, await make_user(conn))
    return {"session": session_id, "app": await make_app(conn)}


def _token(ctx: dict, **overrides: object) -> dict:
    return {
        "hash": SHA,
        "type": "access",
        "session": ctx["session"],
        "app": ctx["app"],
        "jkt": JKT,
        "family": None,
        **overrides,
    }


def _code(ctx: dict, **overrides: object) -> dict:
    return {
        "hash": SHA,
        "app": ctx["app"],
        "session": ctx["session"],
        "challenge": JKT,
        "method": "S256",
        "jkt": JKT,
        **overrides,
    }


# --- sessions ---


@pytest.mark.parametrize("jkt", ["corto", "A" * 44, "A" * 42 + "=", "A" * 42 + "+"])
async def test_sesion_exige_jkt_base64url_de_43(
    conn: AsyncConnection, expect_error: ExpectError, jkt: str
) -> None:
    user_id = await make_user(conn)
    error = await expect_error(
        INSERT_SESSION, {"user": user_id, "jkt": jkt, "secret": random_sha()}
    )
    assert error in (CHECK_VIOLATION, STRING_TOO_LONG)


async def test_sesion_exige_secret_hash(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    user_id = await make_user(conn)
    error = await expect_error(
        INSERT_SESSION, {"user": user_id, "jkt": JKT, "secret": None}
    )
    assert error == NOT_NULL_VIOLATION


@pytest.mark.parametrize("secret", ["cookie-en-claro", "F" * 64, "a" * 65])
async def test_sesion_solo_guarda_hash_sha256_hex_del_secreto(
    conn: AsyncConnection, expect_error: ExpectError, secret: str
) -> None:
    user_id = await make_user(conn)
    error = await expect_error(
        INSERT_SESSION, {"user": user_id, "jkt": JKT, "secret": secret}
    )
    assert error in (CHECK_VIOLATION, STRING_TOO_LONG)


async def test_secret_hash_de_sesion_es_unico(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    user_id = await make_user(conn)
    params = {"user": user_id, "jkt": JKT, "secret": random_sha()}
    await conn.execute(text(INSERT_SESSION), params)
    assert await expect_error(INSERT_SESSION, params) == UNIQUE_VIOLATION


async def test_sesion_nueva_tiene_last_activity_at_y_no_esta_revocada(
    conn: AsyncConnection,
) -> None:
    session_id = await make_session(conn, await make_user(conn))
    row = (
        await conn.execute(
            text(
                "SELECT last_activity_at = created_at, revoked_at FROM sessions "
                "WHERE id = :id"
            ),
            {"id": session_id},
        )
    ).one()
    assert tuple(row) == (True, None)


async def test_revocar_sesion_exige_motivo_valido(
    conn: AsyncConnection, expect_error: ExpectError
) -> None:
    session_id = await make_session(conn, await make_user(conn))
    sql = "UPDATE sessions SET revoked_at = now(), revoked_reason = :r WHERE id = :id"
    assert await expect_error(sql, {"id": session_id, "r": None}) == CHECK_VIOLATION
    assert await expect_error(sql, {"id": session_id, "r": "otro"}) == CHECK_VIOLATION
    assert await expect_error(sql, {"id": session_id, "r": "logout"}) is None


# --- tokens ---


async def test_token_hash_es_unico(
    conn: AsyncConnection, ctx: dict, expect_error: ExpectError
) -> None:
    await conn.execute(text(INSERT_TOKEN), _token(ctx))
    assert await expect_error(INSERT_TOKEN, _token(ctx)) == UNIQUE_VIOLATION


@pytest.mark.parametrize("token_hash", ["token-en-claro", "F" * 64, "a" * 65])
async def test_token_solo_guarda_hash_sha256_hex(
    ctx: dict, expect_error: ExpectError, token_hash: str
) -> None:
    error = await expect_error(INSERT_TOKEN, _token(ctx, hash=token_hash))
    assert error in (CHECK_VIOLATION, STRING_TOO_LONG)


async def test_token_exige_jkt(ctx: dict, expect_error: ExpectError) -> None:
    assert await expect_error(INSERT_TOKEN, _token(ctx, jkt=None)) == NOT_NULL_VIOLATION


async def test_token_rechaza_tipo_desconocido(
    ctx: dict, expect_error: ExpectError
) -> None:
    assert await expect_error(INSERT_TOKEN, _token(ctx, type="id")) == CHECK_VIOLATION


async def test_refresh_exige_familia_y_access_no_la_admite(
    ctx: dict, expect_error: ExpectError
) -> None:
    refresh_without_family = _token(ctx, type="refresh")
    access_with_family = _token(ctx, family="0199f000-0000-7000-8000-000000000000")
    assert await expect_error(INSERT_TOKEN, refresh_without_family) == CHECK_VIOLATION
    assert await expect_error(INSERT_TOKEN, access_with_family) == CHECK_VIOLATION


async def test_rotacion_marca_el_refresh_usado_y_su_reemplazo(
    conn: AsyncConnection, ctx: dict, expect_error: ExpectError
) -> None:
    family = "0199f000-0000-7000-8000-000000000001"
    old_id = (
        await conn.execute(
            text(INSERT_TOKEN + " RETURNING id"),
            _token(ctx, type="refresh", family=family, hash="1" * 64),
        )
    ).scalar_one()
    new_id = (
        await conn.execute(
            text(INSERT_TOKEN + " RETURNING id"),
            _token(ctx, type="refresh", family=family, hash="2" * 64),
        )
    ).scalar_one()
    await conn.execute(
        text(
            "UPDATE tokens SET used_at = now(), replaced_by_id = :new WHERE id = :old"
        ),
        {"new": new_id, "old": old_id},
    )
    family_tokens = (
        await conn.execute(
            text("SELECT count(*) FROM tokens WHERE family_id = :f"), {"f": family}
        )
    ).scalar_one()
    assert family_tokens == 2
    access_id = (
        await conn.execute(text(INSERT_TOKEN + " RETURNING id"), _token(ctx))
    ).scalar_one()
    error = await expect_error(
        "UPDATE tokens SET used_at = now() WHERE id = :id", {"id": access_id}
    )
    assert error == CHECK_VIOLATION


# --- authorization_codes ---


async def test_code_expira_por_defecto_a_los_60_segundos(
    conn: AsyncConnection, ctx: dict
) -> None:
    ttl = (
        await conn.execute(
            text(
                INSERT_CODE + " RETURNING extract(epoch FROM expires_at - created_at)"
            ),
            _code(ctx),
        )
    ).scalar_one()
    assert ttl == 60


async def test_code_no_puede_vivir_mas_de_60_segundos(
    conn: AsyncConnection, ctx: dict, expect_error: ExpectError
) -> None:
    code_id = (
        await conn.execute(text(INSERT_CODE + " RETURNING id"), _code(ctx))
    ).scalar_one()
    error = await expect_error(
        "UPDATE authorization_codes SET expires_at = created_at + "
        "interval '61 seconds' WHERE id = :id",
        {"id": code_id},
    )
    assert error == CHECK_VIOLATION


async def test_code_solo_admite_pkce_s256(ctx: dict, expect_error: ExpectError) -> None:
    assert (
        await expect_error(INSERT_CODE, _code(ctx, method="plain")) == CHECK_VIOLATION
    )


async def test_code_hash_es_unico_y_solo_hash(
    conn: AsyncConnection, ctx: dict, expect_error: ExpectError
) -> None:
    await conn.execute(text(INSERT_CODE), _code(ctx))
    assert await expect_error(INSERT_CODE, _code(ctx)) == UNIQUE_VIOLATION
    assert await expect_error(INSERT_CODE, _code(ctx, hash="b" * 63 + "Z")) == (
        CHECK_VIOLATION
    )


async def test_canje_del_code_es_de_un_solo_uso(
    conn: AsyncConnection, ctx: dict
) -> None:
    code_id = (
        await conn.execute(text(INSERT_CODE + " RETURNING id"), _code(ctx))
    ).scalar_one()
    redeem = text(
        "UPDATE authorization_codes SET used_at = now() WHERE id = :id "
        "AND used_at IS NULL AND expires_at > now() RETURNING id"
    )
    first = (await conn.execute(redeem, {"id": code_id})).all()
    second = (await conn.execute(redeem, {"id": code_id})).all()
    assert (len(first), len(second)) == (1, 0)
