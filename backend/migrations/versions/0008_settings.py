"""settings y settings_history: politicas operativas editables con historial

`settings`: catalogo + valor vigente con CHECK de tipo y rango (int/float/
bool/str). `settings_history`: append-only con los mismos triggers y SQLSTATE
LEO01 que `audit_events` (la funcion `fn_forbid_append_only_change` ya existe
desde 0001). El DDL lo aporta el modulo compartido
`leo_sdk.settings_store.migration` (mismo esquema que en las demas apps). Sin FK de `settings_history.setting_key` a `settings` a
proposito: el historial sobrevive a cambios del catalogo. El downgrade
elimina ambas tablas (y sus triggers) con sus filas.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23 11:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
from leo_sdk.settings_store import migration

# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: str | Sequence[str] | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    migration.upgrade(op, users_table="users")


def downgrade() -> None:
    """Downgrade schema."""
    migration.downgrade(op, users_table="users")
