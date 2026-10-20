"""service grants and service tokens: credenciales de servicio (client credentials)

`service_grants`: rol de OTRA app concedido a una app llamadora (FK compuesta
(role_id, application_id) -> roles; la llamadora no puede ser la destino).
`service_tokens`: tokens de maquina opacos (solo hash SHA-256), vida maxima 1 h.
Solo agrega tablas; el downgrade las elimina con sus filas.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20 17:46:25.913202

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('service_tokens',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('caller_application_id', sa.UUID(), nullable=False),
    sa.Column('audience_application_id', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("expires_at <= created_at + interval '3600 seconds'", name=op.f('ck_service_tokens_ttl_max_1_hour')),
    sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_service_tokens_token_hash_format')),
    sa.CheckConstraint('expires_at > created_at', name=op.f('ck_service_tokens_expires_after_created')),
    sa.ForeignKeyConstraint(['audience_application_id'], ['applications.id'], name=op.f('fk_service_tokens_audience_application_id_applications')),
    sa.ForeignKeyConstraint(['caller_application_id'], ['applications.id'], name=op.f('fk_service_tokens_caller_application_id_applications')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_service_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_service_tokens_token_hash'))
    )
    op.create_index(op.f('ix_service_tokens_audience_application_id'), 'service_tokens', ['audience_application_id'], unique=False)
    op.create_index('ix_service_tokens_caller_audience', 'service_tokens', ['caller_application_id', 'audience_application_id'], unique=False)
    op.create_index(op.f('ix_service_tokens_expires_at'), 'service_tokens', ['expires_at'], unique=False)
    op.create_table('service_grants',
    sa.Column('caller_application_id', sa.UUID(), nullable=False),
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('caller_application_id <> application_id', name=op.f('ck_service_grants_caller_differs_from_target')),
    sa.ForeignKeyConstraint(['caller_application_id'], ['applications.id'], name=op.f('fk_service_grants_caller_application_id_applications')),
    sa.ForeignKeyConstraint(['role_id', 'application_id'], ['roles.id', 'roles.application_id'], name='fk_service_grants_role_id_roles'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_service_grants')),
    sa.UniqueConstraint('caller_application_id', 'role_id', name=op.f('uq_service_grants_caller_application_id'))
    )
    op.create_index('ix_service_grants_role_id', 'service_grants', ['role_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_service_grants_role_id', table_name='service_grants')
    op.drop_table('service_grants')
    op.drop_index(op.f('ix_service_tokens_expires_at'), table_name='service_tokens')
    op.drop_index('ix_service_tokens_caller_audience', table_name='service_tokens')
    op.drop_index(op.f('ix_service_tokens_audience_application_id'), table_name='service_tokens')
    op.drop_table('service_tokens')
