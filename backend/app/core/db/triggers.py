"""SQL de los triggers del esquema + constantes que consume el backend.

Auditoria append-only: `audit_events` lleva triggers que impiden UPDATE,
DELETE (por fila) y TRUNCATE (por sentencia). El error lleva el SQLSTATE
propio `APPEND_ONLY_SQLSTATE`, para que el backend lo mapee a un error de API
y los tests lo distingan de cualquier otro fallo.
"""

APPEND_ONLY_SQLSTATE = "LEO01"
APPEND_ONLY_FUNCTION = "fn_forbid_append_only_change"


def append_only_function_sql() -> str:
    return f"""
CREATE OR REPLACE FUNCTION {APPEND_ONLY_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = '{APPEND_ONLY_SQLSTATE}',
        MESSAGE = format('%s es append-only: %s no permitido', TG_TABLE_NAME, TG_OP);
END;
$$
"""


def drop_append_only_function_sql() -> str:
    return f"DROP FUNCTION IF EXISTS {APPEND_ONLY_FUNCTION}()"


def append_only_trigger_names(table: str) -> tuple[str, str]:
    """(trigger por fila UPDATE/DELETE, trigger por sentencia TRUNCATE)."""
    return f"trg_{table}_append_only", f"trg_{table}_no_truncate"


def append_only_triggers_sql(table: str) -> list[str]:
    row, truncate = append_only_trigger_names(table)
    on_rows = f"BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW"
    on_truncate = f"BEFORE TRUNCATE ON {table} FOR EACH STATEMENT"
    execute = f"EXECUTE FUNCTION {APPEND_ONLY_FUNCTION}()"
    return [
        f"CREATE TRIGGER {row} {on_rows} {execute}",
        f"CREATE TRIGGER {truncate} {on_truncate} {execute}",
    ]


def drop_append_only_triggers_sql(table: str) -> list[str]:
    return [
        f"DROP TRIGGER IF EXISTS {name} ON {table}"
        for name in append_only_trigger_names(table)
    ]
