"""sessions.revoked_reason admite 'email-change'

Al cambiar su correo (exige la contrasena actual), una persona cierra sus
OTRAS sesiones con este motivo, igual que con `password-change`. Reemplaza el
CHECK `ck_sessions_revoked_reason`. Downgrade: las filas con `email-change` se
reasignan a `admin` antes de restaurar el CHECK anterior.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: str | Sequence[str] | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = (
    'logout', 'admin', 'user-deactivated', 'refresh-reuse', 'idle-timeout',
    'password-change',
)
_NEW = (*_OLD, 'email-change')


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
        "WHERE revoked_reason = 'email-change'"
    )
    _replace_check(_OLD)
