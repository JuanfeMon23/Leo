"""SQL del trigger append-only de `settings_history` (el mismo mecanismo que
`audit_events` en Leo: SQLSTATE `LEO01`)."""

APPEND_ONLY_SQLSTATE = "LEO01"
APPEND_ONLY_FUNCTION = "fn_forbid_append_only_change"


def append_only_function_sql(*, if_missing: bool = True) -> str:
    """Crea `fn_forbid_append_only_change()`; con `if_missing` no toca la que
    ya exista (p. ej. la de la migracion inicial de la app)."""
    body = f"""CREATE OR REPLACE FUNCTION {APPEND_ONLY_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = '{APPEND_ONLY_SQLSTATE}',
        MESSAGE = format('%s es append-only: %s no permitido', TG_TABLE_NAME, TG_OP);
END;
$fn$"""
    if not if_missing:
        return body
    return (
        "DO $do$ BEGIN "
        f"IF to_regprocedure('{APPEND_ONLY_FUNCTION}()') IS NULL THEN "
        f"EXECUTE $q${body}$q$; END IF; END $do$"
    )


def append_only_trigger_names(table: str) -> tuple[str, str]:
    return f"trg_{table}_append_only", f"trg_{table}_no_truncate"


def append_only_triggers_sql(table: str) -> list[str]:
    row, truncate = append_only_trigger_names(table)
    execute = f"EXECUTE FUNCTION {APPEND_ONLY_FUNCTION}()"
    on_rows = f"BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW"
    on_truncate = f"BEFORE TRUNCATE ON {table} FOR EACH STATEMENT"
    return [
        f"CREATE TRIGGER {row} {on_rows} {execute}",
        f"CREATE TRIGGER {truncate} {on_truncate} {execute}",
    ]


def drop_append_only_triggers_sql(table: str) -> list[str]:
    return [
        f"DROP TRIGGER IF EXISTS {name} ON {table}"
        for name in append_only_trigger_names(table)
    ]
