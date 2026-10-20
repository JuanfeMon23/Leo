"""Fixtures de los tests de esquema, migraciones y semillas.

Todo corre contra la BD `leo_test` (mismo servidor y credenciales que
`DATABASE_URL`, otro nombre de BD); nunca contra la BD de desarrollo.

- `migrated`: deja `leo_test` en `alembic upgrade head` una vez por sesion
  (crea la BD si no existe).
- `conn`: conexion dentro de una transaccion que se revierte al terminar el
  test (aislamiento sin limpiar a mano).
- `expect_error`: ejecuta SQL en un savepoint y devuelve el SQLSTATE con que
  fallo (la transaccion del test sigue usable).
"""

import hashlib
import os
import subprocess
import sys
from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import pool, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[4]
TEST_DB = "leo_test"

# Thumbprint / code_challenge validos (43 chars base64url) y hash SHA-256 hex.
JKT = "A" * 43
SHA = "a" * 64


def _urls() -> tuple[str, str]:
    """(URL SQLAlchemy de `leo_test`, DSN asyncpg de la BD `postgres`)."""
    base = make_url(get_settings().database_url)
    test_url = base.set(database=TEST_DB).render_as_string(hide_password=False)
    admin_dsn = base.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    return test_url, admin_dsn


TEST_URL, ADMIN_DSN = _urls()


def alembic(*args: str) -> None:
    """Corre Alembic contra `leo_test` en un proceso aparte."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": TEST_URL},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def unique(prefix: str) -> str:
    """Slug/usuario unico (minusculas, kebab-case) para aislar cada test."""
    return f"{prefix}-{uuid4().hex[:12]}"


def sqlstate(exc: DBAPIError) -> str | None:
    """SQLSTATE de un error de asyncpg envuelto por SQLAlchemy."""
    orig = exc.orig
    return getattr(orig, "sqlstate", None) or getattr(
        getattr(orig, "__cause__", None), "sqlstate", None
    )


@pytest_asyncio.fixture(scope="session")
async def migrated() -> None:
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB
        )
        if not exists:
            await admin.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await admin.close()
    alembic("upgrade", "head")


@pytest_asyncio.fixture(scope="session")
async def engine(migrated: None) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(TEST_URL, poolclass=pool.NullPool)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def conn(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


ExpectError = Callable[[str, dict[str, Any] | None], Awaitable[str | None]]


@pytest.fixture
def expect_error(conn: AsyncConnection) -> ExpectError:
    async def run(sql: str, params: dict[str, Any] | None = None) -> str | None:
        savepoint = await conn.begin_nested()
        try:
            await conn.execute(text(sql), params or {})
        except DBAPIError as exc:
            await savepoint.rollback()
            return sqlstate(exc)
        await savepoint.rollback()
        return None

    return run


# --- fabricas minimas por SQL (no dependen de los repositories del backend) ---


async def insert(conn: AsyncConnection, sql: str, **params: Any) -> UUID:
    return (await conn.execute(text(sql + " RETURNING id"), params)).scalar_one()


async def make_app(conn: AsyncConnection, slug: str | None = None) -> UUID:
    slug = slug or unique("app")
    return await insert(
        conn,
        "INSERT INTO applications (slug, name, base_url, client_id, "
        "client_secret_hash) VALUES (:slug, 'App', 'http://x', :slug, :sha)",
        slug=slug,
        sha=SHA,
    )


async def make_module(conn: AsyncConnection, app_id: UUID, slug: str = "mod") -> UUID:
    return await insert(
        conn,
        "INSERT INTO app_modules (application_id, slug, name) "
        "VALUES (:app, :slug, 'Modulo')",
        app=app_id,
        slug=slug,
    )


async def make_action(
    conn: AsyncConnection,
    app_id: UUID,
    module_id: UUID,
    tag: str,
    name: str | None = None,
) -> UUID:
    return await insert(
        conn,
        "INSERT INTO actions (application_id, module_id, verb, tag, name) "
        "VALUES (:app, :mod, split_part(:tag, '.', 3), :tag, :name)",
        app=app_id,
        mod=module_id,
        tag=tag,
        name=name or f"Accion {tag}",
    )


async def make_role(conn: AsyncConnection, app_id: UUID) -> UUID:
    return await insert(
        conn,
        "INSERT INTO roles (application_id, slug, name) VALUES (:app, :slug, 'Rol')",
        app=app_id,
        slug=unique("role"),
    )


async def make_user(conn: AsyncConnection, **overrides: Any) -> UUID:
    username = unique("user")
    values = {
        "username": username,
        "email": f"{username}@example.com",
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
        "document_type": "CC",
        "document_number": uuid4().hex[:20].upper(),
        **overrides,
    }
    return await insert(
        conn,
        "INSERT INTO users (username, email, password_hash, document_type, "
        "document_number, first_name, last_name) VALUES (:username, :email, "
        ":password_hash, :document_type, :document_number, 'Ana', 'Gomez')",
        **values,
    )


def random_sha() -> str:
    """Hash SHA-256 hex distinto en cada llamada (columnas UNIQUE de hashes)."""
    return hashlib.sha256(uuid4().bytes).hexdigest()


async def make_session(conn: AsyncConnection, user_id: UUID) -> UUID:
    return await insert(
        conn,
        "INSERT INTO sessions (user_id, jkt, secret_hash, expires_at) "
        "VALUES (:user, :jkt, :secret, now() + interval '8 hours')",
        user=user_id,
        jkt=JKT,
        secret=random_sha(),
    )
