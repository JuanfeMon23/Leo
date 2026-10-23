"""Helper para la migracion Alembic de cada app.

```python
from leo_sdk.settings_store import migration

def upgrade() -> None:
    migration.upgrade(op)            # tablas + trigger append-only

def downgrade() -> None:
    migration.downgrade(op)
```

Crea `settings` y `settings_history` (mismo DDL que `make_settings_models`,
construido desde el mismo codigo), el indice del historial y los triggers
append-only. `fn_forbid_append_only_change()` se crea solo si no existe.
`users_table` es la tabla de usuarios de la app (PK `id` UUID) a la que
apuntan las FK. No soporta modo offline (`--sql`).
"""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase

from leo_sdk.settings_store.schema import (
    HISTORY_TABLE,
    SETTINGS_TABLE,
    make_settings_models,
)
from leo_sdk.settings_store.triggers import (
    append_only_function_sql,
    append_only_triggers_sql,
    drop_append_only_triggers_sql,
)


def _tables(users_table: str) -> tuple[sa.Table, sa.Table]:
    class _Base(DeclarativeBase):
        pass

    # Tabla de usuarios ficticia: solo para que las FK resuelvan al emitir DDL.
    sa.Table(
        users_table,
        _Base.metadata,
        sa.Column("id", sa.UUID(), primary_key=True),
    )
    models = make_settings_models(_Base, user_pk=f"{users_table}.id")
    return (
        models.Setting.__table__,  # type: ignore[attr-defined]
        models.SettingHistory.__table__,  # type: ignore[attr-defined]
    )


def upgrade(op: Any, *, users_table: str = "users") -> None:
    bind = op.get_bind()
    settings, history = _tables(users_table)
    settings.create(bind)
    history.create(bind)
    op.execute(append_only_function_sql(if_missing=True))
    for statement in append_only_triggers_sql(HISTORY_TABLE):
        op.execute(statement)


def downgrade(op: Any, *, users_table: str = "users") -> None:
    """Elimina ambas tablas (y sus triggers) con sus filas."""
    bind = op.get_bind()
    settings, history = _tables(users_table)
    for statement in drop_append_only_triggers_sql(HISTORY_TABLE):
        op.execute(statement)
    history.drop(bind)
    settings.drop(bind)


__all__ = ["HISTORY_TABLE", "SETTINGS_TABLE", "downgrade", "upgrade"]
