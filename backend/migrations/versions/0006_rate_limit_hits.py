"""rate_limit_hits: limitador de intentos compartido entre procesos

Tabla de aciertos del limitador de ventana deslizante respaldado por
PostgreSQL (`LEO_RATE_LIMIT_BACKEND=postgres`). Solo agrega la tabla y su
indice; el downgrade la elimina.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: str | Sequence[str] | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('rate_limit_hits',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('bucket', sa.String(length=64), nullable=False),
    sa.Column('key', sa.String(length=256), nullable=False),
    sa.Column('hit_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rate_limit_hits'))
    )
    op.create_index('ix_rate_limit_hits_bucket_key_hit_at', 'rate_limit_hits', ['bucket', 'key', 'hit_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_rate_limit_hits_bucket_key_hit_at', table_name='rate_limit_hits')
    op.drop_table('rate_limit_hits')
