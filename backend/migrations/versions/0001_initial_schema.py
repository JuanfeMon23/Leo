"""initial schema: applications, users, roles, auth, audit

Esquema completo de la fase 1. Los enums son varchar + CHECK (nombres de la
convencion `ck_<tabla>_<enum>`). `audit_events` queda append-only con la
funcion `fn_forbid_append_only_change` y sus triggers (UPDATE/DELETE por
fila, TRUNCATE por sentencia), que lanzan SQLSTATE LEO01.

Revision ID: 0001
Revises: 
Create Date: 2026-10-19 10:52:35.825485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.db.triggers import (
    append_only_function_sql,
    append_only_triggers_sql,
    drop_append_only_function_sql,
    drop_append_only_triggers_sql,
)

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('applications',
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('base_url', sa.String(length=512), nullable=False),
    sa.Column('redirect_uris', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('client_id', sa.String(length=64), nullable=False),
    sa.Column('client_secret_hash', sa.String(length=64), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint("btrim(name) <> ''", name=op.f('ck_applications_name_not_blank')),
    sa.CheckConstraint("client_secret_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_applications_client_secret_hash_format')),
    sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f('ck_applications_slug_format')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_applications')),
    sa.UniqueConstraint('client_id', name=op.f('uq_applications_client_id')),
    sa.UniqueConstraint('slug', name=op.f('uq_applications_slug'))
    )
    op.create_table('users',
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('document_type', sa.String(length=8), nullable=False),
    sa.Column('document_number', sa.String(length=32), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('last_name', sa.String(length=100), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_login_attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint("btrim(first_name) <> ''", name=op.f('ck_users_first_name_not_blank')),
    sa.CheckConstraint("btrim(last_name) <> ''", name=op.f('ck_users_last_name_not_blank')),
    sa.CheckConstraint("document_number ~ '^[0-9A-Z]+(-[0-9A-Z]+)*$'", name=op.f('ck_users_document_number_format')),
    sa.CheckConstraint("document_type IN ('CC', 'CE', 'TI', 'RC', 'PA', 'NIT', 'PEP', 'PPT')", name=op.f('ck_users_document_type')),
    sa.CheckConstraint("email ~ '^[^@\\s]+@[^@\\s]+$'", name=op.f('ck_users_email_format')),
    sa.CheckConstraint("password_hash LIKE '$argon2id$%'", name=op.f('ck_users_password_hash_argon2id')),
    sa.CheckConstraint("username ~ '^[a-z0-9]([a-z0-9._-]{1,62})[a-z0-9]$'", name=op.f('ck_users_username_format')),
    sa.CheckConstraint('failed_login_attempts >= 0', name=op.f('ck_users_failed_login_attempts_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('document_type', 'document_number', name=op.f('uq_users_document_type')),
    sa.UniqueConstraint('username', name=op.f('uq_users_username'))
    )
    op.create_index('uq_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=True)
    op.create_table('app_modules',
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint("btrim(name) <> ''", name=op.f('ck_app_modules_name_not_blank')),
    sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f('ck_app_modules_slug_format')),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], name=op.f('fk_app_modules_application_id_applications')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_app_modules')),
    sa.UniqueConstraint('application_id', 'slug', name=op.f('uq_app_modules_application_id')),
    sa.UniqueConstraint('id', 'application_id', name=op.f('uq_app_modules_id'))
    )
    op.create_table('roles',
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint("btrim(name) <> ''", name=op.f('ck_roles_name_not_blank')),
    sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f('ck_roles_slug_format')),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], name=op.f('fk_roles_application_id_applications')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_roles')),
    sa.UniqueConstraint('application_id', 'slug', name=op.f('uq_roles_application_id')),
    sa.UniqueConstraint('id', 'application_id', name=op.f('uq_roles_id'))
    )
    op.create_table('sessions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('jkt', sa.String(length=43), nullable=False),
    sa.Column('ip', postgresql.INET(), nullable=True),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_reason', sa.String(length=32), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("jkt ~ '^[A-Za-z0-9_-]{43}$'", name=op.f('ck_sessions_jkt_format')),
    sa.CheckConstraint("revoked_reason IN ('logout', 'admin', 'user-deactivated', 'refresh-reuse', 'idle-timeout')", name=op.f('ck_sessions_revoked_reason')),
    sa.CheckConstraint('(revoked_at IS NULL) = (revoked_reason IS NULL)', name=op.f('ck_sessions_revoked_at_with_reason')),
    sa.CheckConstraint('expires_at > created_at', name=op.f('ck_sessions_expires_after_created')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_sessions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions'))
    )
    op.create_index(op.f('ix_sessions_expires_at'), 'sessions', ['expires_at'], unique=False)
    op.create_index(op.f('ix_sessions_last_activity_at'), 'sessions', ['last_activity_at'], unique=False)
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table('actions',
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('module_id', sa.UUID(), nullable=False),
    sa.Column('verb', sa.String(length=64), nullable=False),
    sa.Column('tag', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint("split_part(tag, '.', 3) = verb", name=op.f('ck_actions_tag_ends_with_verb')),
    sa.CheckConstraint("tag ~ '^[a-z0-9]+(-[a-z0-9]+)*(\\.[a-z0-9]+(-[a-z0-9]+)*){2}$'", name=op.f('ck_actions_tag_format')),
    sa.CheckConstraint("verb ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f('ck_actions_verb_format')),
    sa.ForeignKeyConstraint(['module_id', 'application_id'], ['app_modules.id', 'app_modules.application_id'], name='fk_actions_module_id_app_modules'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_actions')),
    sa.UniqueConstraint('id', 'application_id', name=op.f('uq_actions_id')),
    sa.UniqueConstraint('module_id', 'verb', name=op.f('uq_actions_module_id')),
    sa.UniqueConstraint('tag', name=op.f('uq_actions_tag'))
    )
    op.create_index('ix_actions_application_id', 'actions', ['application_id'], unique=False)
    op.create_table('audit_events',
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('actor_username', sa.String(length=64), nullable=True),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('module', sa.String(length=64), nullable=True),
    sa.Column('action_tag', sa.String(length=200), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=True),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('result', sa.String(length=16), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('ip', postgresql.INET(), nullable=True),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.Column('session_id', sa.UUID(), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.CheckConstraint("action_tag ~ '^[a-z0-9]+(-[a-z0-9]+)*(\\.[a-z0-9]+(-[a-z0-9]+)*){2}$'", name=op.f('ck_audit_events_action_tag_format')),
    sa.CheckConstraint("changes IS NULL OR jsonb_typeof(changes) = 'object'", name=op.f('ck_audit_events_changes_is_object')),
    sa.CheckConstraint("result IN ('ok', 'denied', 'error')", name=op.f('ck_audit_events_result')),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_events_actor_user_id_users')),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], name=op.f('fk_audit_events_application_id_applications')),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_audit_events_session_id_sessions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    op.create_index('ix_audit_events_action_tag_occurred_at', 'audit_events', ['action_tag', 'occurred_at'], unique=False)
    op.create_index('ix_audit_events_actor_user_id_occurred_at', 'audit_events', ['actor_user_id', 'occurred_at'], unique=False)
    op.create_index('ix_audit_events_application_id_occurred_at', 'audit_events', ['application_id', 'occurred_at'], unique=False)
    op.create_index('ix_audit_events_occurred_at', 'audit_events', ['occurred_at'], unique=False)
    op.create_index('ix_audit_events_session_id', 'audit_events', ['session_id'], unique=False)
    op.create_table('authorization_codes',
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('session_id', sa.UUID(), nullable=False),
    sa.Column('redirect_uri', sa.Text(), nullable=False),
    sa.Column('code_challenge', sa.String(length=43), nullable=False),
    sa.Column('code_challenge_method', sa.String(length=8), server_default=sa.text("'S256'"), nullable=False),
    sa.Column('dpop_jkt', sa.String(length=43), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), server_default=sa.text("now() + interval '60 seconds'"), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("code_challenge ~ '^[A-Za-z0-9_-]{43}$'", name=op.f('ck_authorization_codes_code_challenge_format')),
    sa.CheckConstraint("code_challenge_method = 'S256'", name=op.f('ck_authorization_codes_pkce_s256_only')),
    sa.CheckConstraint("code_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_authorization_codes_code_hash_format')),
    sa.CheckConstraint("dpop_jkt ~ '^[A-Za-z0-9_-]{43}$'", name=op.f('ck_authorization_codes_dpop_jkt_format')),
    sa.CheckConstraint("expires_at > created_at AND expires_at <= created_at + interval '60 seconds'", name=op.f('ck_authorization_codes_ttl_max_60_seconds')),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], name=op.f('fk_authorization_codes_application_id_applications')),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_authorization_codes_session_id_sessions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_authorization_codes')),
    sa.UniqueConstraint('code_hash', name=op.f('uq_authorization_codes_code_hash'))
    )
    op.create_index(op.f('ix_authorization_codes_application_id'), 'authorization_codes', ['application_id'], unique=False)
    op.create_index(op.f('ix_authorization_codes_expires_at'), 'authorization_codes', ['expires_at'], unique=False)
    op.create_index(op.f('ix_authorization_codes_session_id'), 'authorization_codes', ['session_id'], unique=False)
    op.create_table('tokens',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('token_type', sa.String(length=16), nullable=False),
    sa.Column('session_id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('jkt', sa.String(length=43), nullable=False),
    sa.Column('family_id', sa.UUID(), nullable=True),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by_id', sa.UUID(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(token_type = 'refresh') = (family_id IS NOT NULL)", name=op.f('ck_tokens_family_only_for_refresh')),
    sa.CheckConstraint("jkt ~ '^[A-Za-z0-9_-]{43}$'", name=op.f('ck_tokens_jkt_format')),
    sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_tokens_token_hash_format')),
    sa.CheckConstraint("token_type = 'refresh' OR (used_at IS NULL AND replaced_by_id IS NULL)", name=op.f('ck_tokens_rotation_only_for_refresh')),
    sa.CheckConstraint("token_type IN ('access', 'refresh')", name=op.f('ck_tokens_token_type')),
    sa.CheckConstraint('expires_at > created_at', name=op.f('ck_tokens_expires_after_created')),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], name=op.f('fk_tokens_application_id_applications')),
    sa.ForeignKeyConstraint(['replaced_by_id'], ['tokens.id'], name=op.f('fk_tokens_replaced_by_id_tokens')),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_tokens_session_id_sessions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_tokens_token_hash'))
    )
    op.create_index(op.f('ix_tokens_application_id'), 'tokens', ['application_id'], unique=False)
    op.create_index(op.f('ix_tokens_expires_at'), 'tokens', ['expires_at'], unique=False)
    op.create_index('ix_tokens_family_id', 'tokens', ['family_id'], unique=False)
    op.create_index(op.f('ix_tokens_replaced_by_id'), 'tokens', ['replaced_by_id'], unique=False)
    op.create_index(op.f('ix_tokens_session_id'), 'tokens', ['session_id'], unique=False)
    op.create_table('user_roles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_user_roles_role_id_roles')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_roles_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_roles')),
    sa.UniqueConstraint('user_id', 'role_id', name=op.f('uq_user_roles_user_id'))
    )
    op.create_index(op.f('ix_user_roles_role_id'), 'user_roles', ['role_id'], unique=False)
    op.create_table('role_actions',
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('action_id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['action_id', 'application_id'], ['actions.id', 'actions.application_id'], name='fk_role_actions_action_id_actions'),
    sa.ForeignKeyConstraint(['role_id', 'application_id'], ['roles.id', 'roles.application_id'], name='fk_role_actions_role_id_roles'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_role_actions')),
    sa.UniqueConstraint('role_id', 'action_id', name=op.f('uq_role_actions_role_id'))
    )
    op.create_index('ix_role_actions_action_id', 'role_actions', ['action_id'], unique=False)

    # Auditoria append-only (ver app.core.db.triggers).
    op.execute(append_only_function_sql())
    for statement in append_only_triggers_sql('audit_events'):
        op.execute(statement)


def downgrade() -> None:
    """Downgrade schema."""
    for statement in drop_append_only_triggers_sql('audit_events'):
        op.execute(statement)
    op.execute(drop_append_only_function_sql())
    op.drop_index('ix_role_actions_action_id', table_name='role_actions')
    op.drop_table('role_actions')
    op.drop_index(op.f('ix_user_roles_role_id'), table_name='user_roles')
    op.drop_table('user_roles')
    op.drop_index(op.f('ix_tokens_session_id'), table_name='tokens')
    op.drop_index(op.f('ix_tokens_replaced_by_id'), table_name='tokens')
    op.drop_index('ix_tokens_family_id', table_name='tokens')
    op.drop_index(op.f('ix_tokens_expires_at'), table_name='tokens')
    op.drop_index(op.f('ix_tokens_application_id'), table_name='tokens')
    op.drop_table('tokens')
    op.drop_index(op.f('ix_authorization_codes_session_id'), table_name='authorization_codes')
    op.drop_index(op.f('ix_authorization_codes_expires_at'), table_name='authorization_codes')
    op.drop_index(op.f('ix_authorization_codes_application_id'), table_name='authorization_codes')
    op.drop_table('authorization_codes')
    op.drop_index('ix_audit_events_session_id', table_name='audit_events')
    op.drop_index('ix_audit_events_occurred_at', table_name='audit_events')
    op.drop_index('ix_audit_events_application_id_occurred_at', table_name='audit_events')
    op.drop_index('ix_audit_events_actor_user_id_occurred_at', table_name='audit_events')
    op.drop_index('ix_audit_events_action_tag_occurred_at', table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index('ix_actions_application_id', table_name='actions')
    op.drop_table('actions')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_last_activity_at'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_expires_at'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_table('roles')
    op.drop_table('app_modules')
    op.drop_index('uq_users_email_lower', table_name='users')
    op.drop_table('users')
    op.drop_table('applications')
