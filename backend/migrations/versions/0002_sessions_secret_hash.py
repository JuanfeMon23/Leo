"""sessions.secret_hash: hash SHA-256 del secreto de la cookie SSO

La cookie SSO de Leo deja de guardarse como un token `access` de la app
`leo`: la sesion guarda el hash de su propio secreto (UNIQUE, NOT NULL, mismo
CHECK que `token_hash`).

Filas existentes: su secreto en claro no existe en ningun lado, asi que no
hay hash "correcto" posible. Se rellenan con un hash aleatorio unico (ninguna
cookie lo produce) y las que seguian vivas se revocan con motivo `admin`, para
que el estado de la BD diga la verdad (no hay como reanudarlas). No se borran:
`audit_events` (append-only), `tokens` y `authorization_codes` las referencian.
El downgrade solo quita la columna; la revocacion no se deshace.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sessions', sa.Column('secret_hash', sa.String(length=64), nullable=True))
    # Hash aleatorio por fila: sha256 de dos UUID v4 (244 bits aleatorios).
    op.execute(
        "UPDATE sessions SET secret_hash = encode(sha256(convert_to("
        "gen_random_uuid()::text || gen_random_uuid()::text, 'UTF8')), 'hex')"
    )
    op.execute(
        "UPDATE sessions SET revoked_at = now(), revoked_reason = 'admin' "
        "WHERE revoked_at IS NULL"
    )
    op.alter_column('sessions', 'secret_hash', nullable=False)
    op.create_check_constraint(
        op.f('ck_sessions_secret_hash_format'),
        'sessions',
        "secret_hash ~ '^[0-9a-f]{64}$'",
    )
    op.create_unique_constraint(op.f('uq_sessions_secret_hash'), 'sessions', ['secret_hash'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('uq_sessions_secret_hash'), 'sessions', type_='unique')
    op.drop_constraint(op.f('ck_sessions_secret_hash_format'), 'sessions', type_='check')
    op.drop_column('sessions', 'secret_hash')
