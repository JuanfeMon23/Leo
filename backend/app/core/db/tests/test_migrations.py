"""Cadena de migraciones sobre `leo_test`: `upgrade head` coincide con los
modelos, `downgrade base` deja la BD vacia (todo downgrade es real) y las
migraciones con datos (`0002`) tratan bien las filas existentes."""

import re
from uuid import UUID

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.db.registry import Base
from app.core.db.triggers import APPEND_ONLY_FUNCTION

from .conftest import JKT, alembic, insert, make_session, make_user, unique


async def _schema_diff(engine: AsyncEngine) -> list:
    async with engine.connect() as connection:
        return await connection.run_sync(
            lambda sync: compare_metadata(
                MigrationContext.configure(sync), Base.metadata
            )
        )


async def _public_objects(engine: AsyncEngine) -> tuple[list[str], list[str]]:
    async with engine.connect() as connection:
        tables = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        functions = await connection.execute(
            text(
                "SELECT p.proname FROM pg_proc p JOIN pg_namespace n "
                "ON n.oid = p.pronamespace WHERE n.nspname = 'public'"
            )
        )
        return sorted(r[0] for r in tables), sorted(r[0] for r in functions)


async def test_upgrade_head_coincide_con_los_modelos(engine: AsyncEngine) -> None:
    assert await _schema_diff(engine) == []


async def test_upgrade_head_crea_todas_las_tablas_y_la_funcion_append_only(
    engine: AsyncEngine,
) -> None:
    tables, functions = await _public_objects(engine)
    assert set(tables) == set(Base.metadata.tables) | {"alembic_version"}
    assert APPEND_ONLY_FUNCTION in functions


async def test_downgrade_base_vacia_el_esquema_y_upgrade_lo_recrea(
    engine: AsyncEngine,
) -> None:
    alembic("downgrade", "base")
    try:
        tables, functions = await _public_objects(engine)
        assert tables == ["alembic_version"]
        assert functions == []
    finally:
        alembic("upgrade", "head")
    assert await _schema_diff(engine) == []


async def _session_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'sessions'"
            )
        )
        return {r[0] for r in rows}


async def test_0002_rellena_secret_hash_y_revoca_sesiones_previas(
    engine: AsyncEngine,
) -> None:
    """Las sesiones creadas antes de `0002` no tienen secreto conocido: quedan
    con un hash aleatorio unico (ninguna cookie lo produce) y, si seguian
    vivas, revocadas por `admin`. Las ya revocadas conservan su motivo."""
    alembic("downgrade", "0001")
    user_id = None
    try:
        async with engine.begin() as connection:
            user_id = await make_user(connection)
            live = await make_session_0001(connection, user_id)
            closed = await make_session_0001(connection, user_id)
            await connection.execute(
                text(
                    "UPDATE sessions SET revoked_at = now(), "
                    "revoked_reason = 'logout' WHERE id = :id"
                ),
                {"id": closed},
            )
        alembic("upgrade", "head")
        async with engine.connect() as connection:
            rows = {
                r.id: r
                for r in await connection.execute(
                    text(
                        "SELECT id, secret_hash, revoked_at, revoked_reason "
                        "FROM sessions WHERE user_id = :u"
                    ),
                    {"u": user_id},
                )
            }
        assert all(re.fullmatch(r"[0-9a-f]{64}", r.secret_hash) for r in rows.values())
        assert rows[live].secret_hash != rows[closed].secret_hash
        assert rows[live].revoked_at is not None
        assert rows[live].revoked_reason == "admin"
        assert rows[closed].revoked_reason == "logout"

        alembic("downgrade", "0001")
        assert "secret_hash" not in await _session_columns(engine)
    finally:
        alembic("upgrade", "head")
        if user_id is not None:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM sessions WHERE user_id = :u"), {"u": user_id}
                )
                await connection.execute(
                    text("DELETE FROM users WHERE id = :u"), {"u": user_id}
                )
    assert "secret_hash" in await _session_columns(engine)
    assert await _schema_diff(engine) == []


async def make_session_0001(connection: AsyncConnection, user_id: UUID) -> UUID:
    """Sesion con el esquema de `0001` (sin `secret_hash`)."""
    return await insert(
        connection,
        "INSERT INTO sessions (user_id, jkt, expires_at) "
        "VALUES (:user, :jkt, now() + interval '8 hours')",
        user=user_id,
        jkt=JKT,
    )


async def _public_tables(engine: AsyncEngine) -> set[str]:
    return set((await _public_objects(engine))[0])


async def test_0004_sube_y_baja_con_datos_reales(engine: AsyncEngine) -> None:
    """`0004` solo agrega tablas: las filas existentes quedan intactas, el
    downgrade quita `service_*` (con sus filas) y volver a subir las recrea."""
    alembic("downgrade", "0003")
    app_ids: list[UUID] = []
    try:
        assert not {"service_grants", "service_tokens"} & await _public_tables(engine)
        async with engine.begin() as connection:
            for _ in range(2):
                app_ids.append(
                    await insert(
                        connection,
                        "INSERT INTO applications (slug, name, base_url, "
                        "client_id, client_secret_hash) VALUES (:s, 'A', "
                        "'http://x', :s, :sha)",
                        s=unique("app"),
                        sha="a" * 64,
                    )
                )
        alembic("upgrade", "head")
        async with engine.begin() as connection:
            role = await insert(
                connection,
                "INSERT INTO roles (application_id, slug, name) "
                "VALUES (:a, 'r', 'Rol')",
                a=app_ids[1],
            )
            await connection.execute(
                text(
                    "INSERT INTO service_grants (caller_application_id, role_id, "
                    "application_id) VALUES (:c, :r, :t)"
                ),
                {"c": app_ids[0], "r": role, "t": app_ids[1]},
            )
            await connection.execute(
                text(
                    "INSERT INTO service_tokens (token_hash, "
                    "caller_application_id, audience_application_id, expires_at) "
                    "VALUES (:h, :c, :t, now() + interval '10 minutes')"
                ),
                {"h": "b" * 64, "c": app_ids[0], "t": app_ids[1]},
            )
        async with engine.connect() as connection:
            kept = (
                await connection.execute(
                    text("SELECT count(*) FROM applications WHERE id = ANY(:a)"),
                    {"a": app_ids},
                )
            ).scalar_one()
        assert kept == 2

        alembic("downgrade", "0003")
        assert not {"service_grants", "service_tokens"} & await _public_tables(engine)
        async with engine.connect() as connection:
            kept = (
                await connection.execute(
                    text("SELECT count(*) FROM applications WHERE id = ANY(:a)"),
                    {"a": app_ids},
                )
            ).scalar_one()
        assert kept == 2
    finally:
        alembic("upgrade", "head")
        async with engine.begin() as connection:
            for table, column in (
                ("service_tokens", "caller_application_id"),
                ("service_grants", "caller_application_id"),
                ("roles", "application_id"),
                ("applications", "id"),
            ):
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE {column} = ANY(:a)"),
                    {"a": app_ids},
                )
    assert {"service_grants", "service_tokens"} <= await _public_tables(engine)
    assert await _schema_diff(engine) == []


async def _action_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'actions'"
            )
        )
        return {r[0] for r in rows}


async def test_0003_rellena_nombre_de_acciones_existentes(
    engine: AsyncEngine,
) -> None:
    """Las acciones previas a `0003` quedan con nombre: las `leo.*` con el del
    catalogo, las demas con el verbo capitalizado y con espacios."""
    alembic("downgrade", "0002")
    app_ids: list[UUID] = []
    try:
        async with engine.begin() as connection:
            for slug, modules in (
                ("leo", {"users": ["view", "reset-password"]}),
                (unique("tool"), {"items": ["rotate-secret", "view"]}),
            ):
                app_id = await insert(
                    connection,
                    "INSERT INTO applications (slug, name, base_url, client_id, "
                    "client_secret_hash) VALUES (:s, 'A', 'http://x', :s, :sha)",
                    s=slug,
                    sha="a" * 64,
                )
                app_ids.append(app_id)
                for module, verbs in modules.items():
                    module_id = await insert(
                        connection,
                        "INSERT INTO app_modules (application_id, slug, name) "
                        "VALUES (:a, :m, 'M')",
                        a=app_id,
                        m=module,
                    )
                    for verb in verbs:
                        await connection.execute(
                            text(
                                "INSERT INTO actions (application_id, module_id, "
                                "verb, tag) VALUES (:a, :m, :v, :t)"
                            ),
                            {
                                "a": app_id,
                                "m": module_id,
                                "v": verb,
                                "t": f"{slug}.{module}.{verb}",
                            },
                        )
        alembic("upgrade", "head")
        async with engine.connect() as connection:
            names = {
                r.tag: r.name
                for r in await connection.execute(
                    text(
                        "SELECT tag, name FROM actions WHERE application_id = ANY(:a)"
                    ),
                    {"a": app_ids},
                )
            }
        tool = next(t.split(".")[0] for t in names if not t.startswith("leo."))
        assert names["leo.users.view"] == "Consultar usuarios"
        assert names["leo.users.reset-password"] == "Restablecer contraseñas"
        assert names[f"{tool}.items.rotate-secret"] == "Rotate secret"
        assert names[f"{tool}.items.view"] == "View"

        alembic("downgrade", "0002")
        assert "name" not in await _action_columns(engine)
    finally:
        alembic("upgrade", "head")
        async with engine.begin() as connection:
            for table, column in (
                ("actions", "application_id"),
                ("app_modules", "application_id"),
                ("applications", "id"),
            ):
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE {column} = ANY(:a)"),
                    {"a": app_ids},
                )
    assert "name" in await _action_columns(engine)
    assert await _schema_diff(engine) == []


async def test_0005_admite_password_change_y_el_downgrade_lo_reasigna_a_admin(
    engine: AsyncEngine,
) -> None:
    """`0005` agrega el motivo `password-change`; al bajar, las filas que lo
    usan pasan a `admin` (el CHECK antiguo no lo admite) y el resto se conserva."""
    user_id = None
    try:
        async with engine.begin() as connection:
            user_id = await make_user(connection)
            changed = await make_session(connection, user_id)
            closed = await make_session(connection, user_id)
        async with engine.begin() as connection:
            for sid, reason in ((changed, "password-change"), (closed, "logout")):
                await connection.execute(
                    text(
                        "UPDATE sessions SET revoked_at = now(), "
                        "revoked_reason = :r WHERE id = :id"
                    ),
                    {"r": reason, "id": sid},
                )
        alembic("downgrade", "0004")
        async with engine.connect() as connection:
            reasons = {
                r.id: r.revoked_reason
                for r in await connection.execute(
                    text("SELECT id, revoked_reason FROM sessions WHERE user_id = :u"),
                    {"u": user_id},
                )
            }
        assert reasons == {changed: "admin", closed: "logout"}
        alembic("upgrade", "head")
    finally:
        alembic("upgrade", "head")
        if user_id is not None:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM sessions WHERE user_id = :u"), {"u": user_id}
                )
                await connection.execute(
                    text("DELETE FROM users WHERE id = :u"), {"u": user_id}
                )
    assert await _schema_diff(engine) == []


async def test_0008_sube_y_baja_ajustes_con_su_historial(engine: AsyncEngine) -> None:
    """`0008` solo agrega `settings` y `settings_history` (con sus triggers);
    el downgrade las quita con sus filas y volver a subir las recrea."""
    new_tables = {"settings", "settings_history"}
    alembic("downgrade", "0007")
    try:
        assert not new_tables & await _public_tables(engine)
        alembic("upgrade", "head")
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO settings (key, value, value_type, default_value, "
                    "group_name, description) VALUES ('a.b', '1', 'int', '1', "
                    "'g', 'd')"
                )
            )
        alembic("downgrade", "0007")
        assert not new_tables & await _public_tables(engine)
    finally:
        alembic("upgrade", "head")
    assert new_tables <= await _public_tables(engine)
    async with engine.connect() as connection:
        rows = (await connection.execute(text("SELECT count(*) FROM settings"))).scalar_one()
        triggers = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM pg_trigger WHERE tgrelid = "
                    "'settings_history'::regclass AND NOT tgisinternal"
                )
            )
        ).scalar_one()
    assert (rows, triggers) == (0, 2)
    assert await _schema_diff(engine) == []
