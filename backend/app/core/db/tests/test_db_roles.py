"""`deploy/db_roles.sql`: roles de minimo privilegio.

Corre el script contra una BD temporal (`leo_roles_test`, migrada con
`MIGRATION_DATABASE_URL` mientras `DATABASE_URL` apunta a un servidor
inexistente, para probar tambien `migrations/env.py`) y verifica con
`SET ROLE` lo que `leo_app` puede y no puede hacer. Si los roles no existian
en el servidor, el test los borra al terminar.
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncGenerator

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url

from .conftest import ADMIN_DSN, BACKEND_DIR

ROLES_DB = "leo_roles_test"
SCRIPT = (BACKEND_DIR / "deploy" / "db_roles.sql").read_text(encoding="utf-8")
INSUFFICIENT_PRIVILEGE = "42501"
SHA = "a" * 64


def _dsn(database: str, driver: str) -> str:
    url = make_url(ADMIN_DSN).set(drivername=driver, database=database)
    return url.render_as_string(hide_password=False)


async def _sqlstate(conn: asyncpg.Connection, role: str, sql: str) -> str | None:
    """SQLSTATE con que falla `sql` ejecutado como `role` (None si funciona)."""
    await conn.execute(f"SET ROLE {role}")
    try:
        await conn.execute(sql)
    except asyncpg.PostgresError as exc:
        return exc.sqlstate
    finally:
        await conn.execute("RESET ROLE")
    return None


@pytest_asyncio.fixture(scope="module")
async def roles_db() -> AsyncGenerator[asyncpg.Connection]:
    admin = await asyncpg.connect(ADMIN_DSN)
    existing = {
        r["rolname"]
        for r in await admin.fetch(
            "SELECT rolname FROM pg_roles WHERE rolname IN ('leo_app', 'leo_migrator')"
        )
    }
    await admin.execute(f'DROP DATABASE IF EXISTS "{ROLES_DB}" WITH (FORCE)')
    await admin.execute(f'CREATE DATABASE "{ROLES_DB}"')
    conn = None
    try:
        migration = _dsn(ROLES_DB, "postgresql+asyncpg")
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env={
                **os.environ,
                "DATABASE_URL": "postgresql+asyncpg://nadie:x@127.0.0.1:1/nada",
                "MIGRATION_DATABASE_URL": migration,
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        conn = await asyncpg.connect(_dsn(ROLES_DB, "postgresql"))
        await conn.execute(SCRIPT)
        yield conn
    finally:
        if conn is not None:
            await conn.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{ROLES_DB}" WITH (FORCE)')
        for role in ("leo_app", "leo_migrator"):
            if role not in existing:
                await admin.execute(f"DROP ROLE IF EXISTS {role}")
        await admin.close()


async def test_alembic_uso_migration_database_url(roles_db) -> None:
    assert await roles_db.fetchval("SELECT count(*) FROM alembic_version") == 1


async def test_el_script_es_idempotente(roles_db) -> None:
    await roles_db.execute(SCRIPT)
    await roles_db.execute(SCRIPT)


async def test_leo_app_no_tiene_privilegios_de_rol(roles_db) -> None:
    for role in ("leo_app", "leo_migrator"):
        row = await roles_db.fetchrow(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
            "rolbypassrls FROM pg_roles WHERE rolname = $1",
            role,
        )
        assert not any(row.values()), role
    assert not await roles_db.fetchval(
        "SELECT pg_has_role('leo_app', 'leo_migrator', 'MEMBER')"
    )


async def test_leo_migrator_es_duenio_del_esquema_y_las_tablas(roles_db) -> None:
    owners = {
        r["tableowner"]
        for r in await roles_db.fetch(
            "SELECT tableowner FROM pg_tables WHERE schemaname = 'public'"
        )
    }
    assert owners == {"leo_migrator"}
    schema_owner = await roles_db.fetchval(
        "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'public'"
    )
    assert schema_owner == "leo_migrator"


async def test_leo_app_opera_las_tablas_normales(roles_db) -> None:
    await roles_db.execute("SET ROLE leo_app")
    try:
        app_id = await roles_db.fetchval(
            "INSERT INTO applications (slug, name, base_url, client_id, "
            "client_secret_hash) VALUES ('roles-test', 'Roles', 'http://x', "
            "'roles-test', $1) RETURNING id",
            SHA,
        )
        await roles_db.execute(
            "UPDATE applications SET name = 'Otro' WHERE id = $1", app_id
        )
        assert (
            await roles_db.fetchval(
                "SELECT name FROM applications WHERE id = $1", app_id
            )
            == "Otro"
        )
        await roles_db.execute("DELETE FROM applications WHERE id = $1", app_id)
        # Tabla con secuencia (identity): exige USAGE en la secuencia.
        await roles_db.execute(
            "INSERT INTO rate_limit_hits (bucket, key, hit_at) "
            "VALUES ('roles-test', 'k', now())"
        )
        await roles_db.execute(
            "DELETE FROM rate_limit_hits WHERE bucket = 'roles-test'"
        )
    finally:
        await roles_db.execute("RESET ROLE")


async def test_audit_events_solo_select_e_insert(roles_db) -> None:
    app_id = await roles_db.fetchval(
        "INSERT INTO applications (slug, name, base_url, client_id, "
        "client_secret_hash) VALUES ('audit-test', 'Audit', 'http://x', "
        "'audit-test', $1) RETURNING id",
        SHA,
    )
    # Las filas de auditoria son inmutables: la BD temporal se descarta al final.
    await roles_db.execute("SET ROLE leo_app")
    try:
        event_id = await roles_db.fetchval(
            "INSERT INTO audit_events (application_id, action_tag, result) "
            "VALUES ($1, 'leo.users.edit', 'ok') RETURNING id",
            app_id,
        )
        assert await roles_db.fetchval(
            "SELECT count(*) FROM audit_events WHERE id = $1", event_id
        )
    finally:
        await roles_db.execute("RESET ROLE")
    for sql in (
        "UPDATE audit_events SET result = 'denied'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
        "DROP TABLE audit_events",
        "ALTER TABLE audit_events DISABLE TRIGGER ALL",
        "ALTER TABLE audit_events ADD COLUMN x int",
    ):
        assert await _sqlstate(roles_db, "leo_app", sql) == INSUFFICIENT_PRIVILEGE, sql


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users",
        "ALTER TABLE users ADD COLUMN x int",
        "TRUNCATE users",
        "CREATE TABLE intruso (id int)",
        "DROP SCHEMA public CASCADE",
        "CREATE INDEX ix_intruso ON users (username)",
        "SELECT * FROM alembic_version",
        "CREATE ROLE intruso",
    ],
)
async def test_leo_app_no_puede_ddl_ni_truncate(roles_db, sql: str) -> None:
    assert await _sqlstate(roles_db, "leo_app", sql) == INSUFFICIENT_PRIVILEGE


async def test_leo_migrator_hace_ddl_y_las_tablas_nuevas_requieren_reaplicar(
    roles_db,
) -> None:
    create = "CREATE TABLE tabla_nueva (id serial PRIMARY KEY, v text)"
    assert await _sqlstate(roles_db, "leo_migrator", create) is None
    try:
        # Falla cerrada: la tabla nueva no es accesible hasta re-aplicar el script.
        assert (
            await _sqlstate(roles_db, "leo_app", "SELECT * FROM tabla_nueva")
            == INSUFFICIENT_PRIVILEGE
        )
        await roles_db.execute(SCRIPT)
        assert await _sqlstate(roles_db, "leo_app", "SELECT * FROM tabla_nueva") is None
        assert (
            await _sqlstate(
                roles_db, "leo_app", "INSERT INTO tabla_nueva (v) VALUES ('x')"
            )
            is None
        )
    finally:
        assert (
            await _sqlstate(roles_db, "leo_migrator", "DROP TABLE tabla_nueva") is None
        )
