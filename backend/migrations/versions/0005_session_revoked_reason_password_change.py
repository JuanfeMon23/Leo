"""sessions.revoked_reason admite 'password-change'

Al cambiar su contrasena, una persona cierra sus OTRAS sesiones con este
motivo. Reemplaza el CHECK `ck_sessions_revoked_reason` (varchar + CHECK, sin
tipo nativo). Downgrade: las filas con `password-change` se reasignan a
`admin` (motivo mas cercano: cierre forzado por tercero) antes de restaurar
el CHECK antiguo, que no admite el valor nuevo.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = ('logout', 'admin', 'user-deactivated', 'refresh-reuse', 'idle-timeout')
_NEW = (*_OLD, 'password-change')


def _check(values: tuple[str, ...]) -> str:
    return 'revoked_reason IN (' + ', '.join(f"'{v}'" for v in values) + ')'


def _replace_check(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f('ck_sessions_revoked_reason'), 'sessions', type_='check')
    op.create_check_constraint(
        op.f('ck_sessions_revoked_reason'), 'sessions', _check(values)
    )


def upgrade() -> None:
    """Upgrade schema."""
    _replace_check(_NEW)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE sessions SET revoked_reason = 'admin' "
        "WHERE revoked_reason = 'password-change'"
    )
    _replace_check(_OLD)
