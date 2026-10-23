"""Modo sin FK (`user_pk=None` / `users_table=None`) y modo con FK intacto.

El modo sin FK se crea en un esquema temporal (`nofk`) dentro de la
transaccion revertida del test, para no chocar con las tablas con FK.
"""

from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import DeclarativeBase

from leo_sdk.settings_store import (
    SettingsActor,
    SettingsRegistry,
    SettingsStore,
    make_settings_models,
    migration,
)

from .conftest import REGISTRY_DEFS


class NoFkBase(DeclarativeBase):
    pass


NO_FK = make_settings_models(NoFkBase, user_pk=None)


def _fks(sync_conn, table):
    return inspect(sync_conn).get_foreign_keys(table, schema="nofk")


def _constraints(sync_conn, schema):
    rows = sync_conn.execute(
        text(
            "SELECT conname FROM pg_constraint WHERE conrelid IN "
            "(to_regclass(:s || '.settings'), to_regclass(:s || '.settings_history'))"
        ),
        {"s": schema},
    )
    return {r[0] for r in rows}


def test_models_without_fk_have_plain_uuid_columns():
    for model, col in ((NO_FK.Setting, "updated_by"), (NO_FK.SettingHistory, "changed_by")):
        column = model.__table__.c[col]
        assert not column.foreign_keys
        assert column.nullable
        assert column.type.python_type.__name__ == "UUID"


def test_models_with_fk_unchanged():
    class B(DeclarativeBase):
        pass

    m = make_settings_models(B)
    assert {fk.target_fullname for fk in m.Setting.__table__.c.updated_by.foreign_keys} == {"users.id"}
    assert {fk.target_fullname for fk in m.SettingHistory.__table__.c.changed_by.foreign_keys} == {"users.id"}


@pytest.fixture
async def nofk_session(session):
    await session.execute(text("CREATE SCHEMA nofk"))
    await session.execute(text("SET LOCAL search_path TO nofk, public"))

    def run(sync_conn):
        with Operations.context(MigrationContext.configure(sync_conn)) as ops:
            migration.upgrade(ops, users_table=None)

    await (await session.connection()).run_sync(run)
    return session


async def test_migration_without_fk_same_schema_but_no_fk(nofk_session):
    conn = await nofk_session.connection()

    def check(sync_conn):
        assert _fks(sync_conn, "settings") == []
        assert _fks(sync_conn, "settings_history") == []
        no_fk = _constraints(sync_conn, "nofk")
        with_fk = _constraints(sync_conn, "public")
        assert no_fk == {c for c in with_fk if not c.startswith("fk_")}
        assert {i["name"] for i in inspect(sync_conn).get_indexes("settings_history", schema="nofk")} == {
            "ix_settings_history_setting_key_changed_at"
        }

    await conn.run_sync(check)
    triggers = {
        r[0]
        for r in await nofk_session.execute(
            text(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
                "AND tgrelid = 'nofk.settings_history'::regclass"
            )
        )
    }
    assert triggers == {"trg_settings_history_append_only", "trg_settings_history_no_truncate"}


async def test_store_writes_arbitrary_uuid_actor(nofk_session, shared_factory, clock):
    registry = SettingsRegistry(REGISTRY_DEFS)
    store = SettingsStore(registry, shared_factory, NO_FK, cache_ttl=10, monotonic=clock)
    await store.sync_registry()
    actor_id = uuid4()  # no existe en ninguna tabla de usuarios
    await store.update(
        "ui.title", "Nuevo", reason="cambio de prueba",
        actor=SettingsActor(actor_id, "ana", "req-1"), expected_version=1,
    )
    s = NO_FK.Setting
    assert (await nofk_session.execute(select(s.updated_by).where(s.key == "ui.title"))).scalar_one() == actor_id
    h = NO_FK.SettingHistory
    assert (await nofk_session.execute(select(h.changed_by).where(h.setting_key == "ui.title"))).scalar_one() == actor_id


async def test_downgrade_without_fk(nofk_session):
    def run(sync_conn):
        with Operations.context(MigrationContext.configure(sync_conn)) as ops:
            migration.downgrade(ops, users_table=None)
        assert sync_conn.execute(text("SELECT to_regclass('nofk.settings')")).scalar() is None

    await (await nofk_session.connection()).run_sync(run)
