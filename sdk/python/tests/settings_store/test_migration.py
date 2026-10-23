"""Helper de migracion: crea/elimina tablas, indice y triggers; nombres
explicitos aunque la Base no tenga convencion de nombres."""

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from leo_sdk.settings_store import migration

CONSTRAINTS = {
    "pk_settings",
    "ck_settings_key_format",
    "ck_settings_value_type",
    "ck_settings_typed_values",
    "ck_settings_value_in_range",
    "ck_settings_version_positive",
    "ck_settings_group_name_not_blank",
    "fk_settings_updated_by_users",
    "pk_settings_history",
    "ck_settings_history_reason_min_length",
    "ck_settings_history_version_after_positive",
    "fk_settings_history_changed_by_users",
}


async def names(session, sql):
    return {r[0] for r in (await session.execute(text(sql))).all()}


async def test_schema_has_explicit_names_index_and_triggers(session):
    assert CONSTRAINTS <= await names(
        session,
        "SELECT conname FROM pg_constraint WHERE conrelid::regclass::text "
        "IN ('settings', 'settings_history')",
    )
    assert "ix_settings_history_setting_key_changed_at" in await names(
        session, "SELECT indexname FROM pg_indexes WHERE tablename = 'settings_history'"
    )
    assert await names(
        session,
        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
        "AND tgrelid = 'settings_history'::regclass",
    ) == {"trg_settings_history_append_only", "trg_settings_history_no_truncate"}


async def test_downgrade_then_upgrade_roundtrip(session):
    def run(sync_conn):
        with Operations.context(MigrationContext.configure(sync_conn)) as ops:
            migration.downgrade(ops)
            assert (
                sync_conn.execute(text("SELECT to_regclass('settings')")).scalar()
                is None
            )
            migration.upgrade(ops)
            assert sync_conn.execute(text("SELECT to_regclass('settings')")).scalar()

    conn = await session.connection()
    await conn.run_sync(run)
    assert (await session.execute(text("SELECT count(*) FROM settings"))).scalar() == 0
