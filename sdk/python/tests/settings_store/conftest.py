"""Fixtures de `settings_store`: BD PostgreSQL propia (`leo_sdk_settings_test`).

El DSN sale de `SETTINGS_TEST_DATABASE_URL` o, si no, de `DATABASE_URL` (entorno
o `backend/.env`) cambiando solo el nombre de la BD; nunca toca otra BD. Sin
DSN o sin servidor, estos tests se omiten. El esquema se crea UNA vez con el
helper de migracion (`migration.upgrade`) y cada test corre dentro de una
transaccion que se revierte.
"""

import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import UUID as SAUUID
from sqlalchemy import Column, Table, pool, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from leo_sdk.settings_store import (
    SettingDef,
    SettingsRegistry,
    SettingsStore,
    make_settings_models,
    migration,
)

TEST_DB = "leo_sdk_settings_test"
BACKEND_ENV = Path(__file__).resolve().parents[4] / "backend" / ".env"


def _base_url() -> str | None:
    if os.environ.get("SETTINGS_TEST_DATABASE_URL"):
        return os.environ["SETTINGS_TEST_DATABASE_URL"]
    dsn = os.environ.get("DATABASE_URL")
    if not dsn and BACKEND_ENV.exists():
        from dotenv import dotenv_values

        dsn = dotenv_values(BACKEND_ENV).get("DATABASE_URL")
    return dsn


def _urls() -> tuple[str, str] | None:
    dsn = _base_url()
    if dsn is None:
        return None
    base = make_url(dsn)
    test = base.set(database=TEST_DB).render_as_string(hide_password=False)
    admin = base.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    return test, admin


URLS = _urls()
if URLS is None:
    collect_ignore_glob = ["test_*.py"]


class Base(DeclarativeBase):
    """Base SIN convencion de nombres: prueba que los nombres son explicitos."""


_users = Table(
    "users", Base.metadata, Column("id", SAUUID(as_uuid=True), primary_key=True)
)
MODELS = make_settings_models(Base)


def _migrate(sync_conn) -> None:
    sync_conn.execute(text("DROP SCHEMA public CASCADE"))
    sync_conn.execute(text("CREATE SCHEMA public"))
    sync_conn.execute(text("CREATE TABLE users (id uuid PRIMARY KEY DEFAULT uuidv7())"))
    ctx = MigrationContext.configure(sync_conn)
    with Operations.context(ctx) as ops:
        migration.upgrade(ops)


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine]:
    assert URLS is not None
    test_url, admin_dsn = URLS
    try:
        admin = await asyncpg.connect(admin_dsn, timeout=5)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Sin PostgreSQL disponible: {exc}")
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname=$1", TEST_DB
        )
        if not exists:
            await admin.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await admin.close()
    eng = create_async_engine(test_url, poolclass=pool.NullPool)
    async with eng.begin() as conn:
        await conn.run_sync(_migrate)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    async with engine.connect() as connection:
        outer = await connection.begin()
        maker = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with maker() as s:
            yield s
        await outer.rollback()


@pytest.fixture
def shared_factory(session: AsyncSession) -> Callable:
    """Factoria de sesiones que reusa la sesion del test (sin cerrarla)."""

    @asynccontextmanager
    async def factory() -> AsyncGenerator[AsyncSession]:
        yield session

    return factory


REGISTRY_DEFS = (
    SettingDef(
        "auth.max_attempts",
        "int",
        5,
        "Intentos antes del bloqueo.",
        min=3,
        max=20,
        unit="count",
        group="auth",
        requires_security=True,
    ),
    SettingDef(
        "auth.idle_minutes",
        "int",
        30,
        "Inactividad máxima.",
        min=5,
        max=120,
        unit="minutes",
        group="auth",
    ),
    SettingDef("ui.ratio", "float", 1.5, "Razón.", min=0.5, max=3.0, group="ui"),
    SettingDef("ui.compact", "bool", False, "Modo compacto.", group="ui"),
    SettingDef("ui.title", "str", "Hola", "Título.", group="ui"),
)


@pytest.fixture
def registry() -> SettingsRegistry:
    return SettingsRegistry(REGISTRY_DEFS)


class Clock:
    """Reloj manual para el TTL de la cache."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest_asyncio.fixture
async def store(registry, shared_factory, clock) -> SettingsStore:
    s = SettingsStore(registry, shared_factory, MODELS, cache_ttl=10, monotonic=clock)
    await s.sync_registry()
    return s


@pytest_asyncio.fixture
async def user_id(session: AsyncSession) -> UUID:
    uid = uuid4()
    await session.execute(text("INSERT INTO users (id) VALUES (:i)"), {"i": uid})
    return uid
