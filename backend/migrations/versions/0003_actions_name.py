"""actions.name: nombre legible en espanol de cada accion

El tag sigue siendo el identificador unico; `name` (varchar(120), NOT NULL,
no vacio, UNIQUE por modulo) es lo que lee quien administra roles.

Filas existentes: las acciones `leo.*` toman el nombre del catalogo de la
semilla (copiado aqui: una migracion no debe depender del codigo vivo); las
demas, el verbo con espacios y la primera letra en mayuscula (`rotate-secret`
-> `Rotate secret`). Si dos acciones de un modulo derivaran el mismo nombre
(verbos que solo difieren en guiones), la segunda lleva el verbo original
entre parentesis para respetar la unicidad. El downgrade quita restricciones
y columna.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEO_ACTION_NAMES = {
    'leo.applications.view': 'Consultar aplicaciones',
    'leo.applications.create': 'Crear aplicaciones',
    'leo.applications.edit': 'Editar aplicaciones',
    'leo.applications.deactivate': 'Desactivar y reactivar aplicaciones',
    'leo.applications.rotate-secret': 'Rotar el secreto de una aplicación',
    'leo.applications.sync-catalog': 'Evento: sincronización de catálogo',
    'leo.users.view': 'Consultar usuarios',
    'leo.users.create': 'Crear usuarios',
    'leo.users.edit': 'Editar usuarios',
    'leo.users.deactivate': 'Desactivar y reactivar usuarios',
    'leo.users.unlock': 'Desbloquear usuarios',
    'leo.users.reset-password': 'Restablecer contraseñas',
    'leo.users.assign-roles': 'Asignar roles a usuarios',
    'leo.roles.view': 'Consultar roles',
    'leo.roles.create': 'Crear roles',
    'leo.roles.edit': 'Editar roles',
    'leo.roles.deactivate': 'Desactivar y reactivar roles',
    'leo.auth.view': 'Consultar sesiones',
    'leo.auth.revoke': 'Cerrar sesiones de otros usuarios',
    'leo.auth.login': 'Evento: inicio de sesión',
    'leo.auth.logout': 'Evento: cierre de sesión',
    'leo.auth.lock': 'Evento: bloqueo por intentos fallidos',
    'leo.auth.idle-timeout': 'Evento: cierre por inactividad',
    'leo.auth.refresh-reuse': 'Evento: reutilización de token',
    'leo.auth.token': 'Evento: emisión de tokens',
    'leo.auth.authorize': 'Evento: autorización de acceso',
    'leo.audit.view': 'Consultar auditoría',
    'leo.audit.export': 'Exportar auditoría',
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('actions', sa.Column('name', sa.String(length=120), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(
        sa.text('SELECT id, module_id, verb, tag FROM actions ORDER BY created_at, id')
    ).all()
    used: set[tuple] = set()
    for row in rows:
        name = _LEO_ACTION_NAMES.get(row.tag) or row.verb.replace('-', ' ').capitalize()
        if (row.module_id, name) in used:
            name = f'{name} ({row.verb})'
        used.add((row.module_id, name))
        conn.execute(
            sa.text('UPDATE actions SET name = :name WHERE id = :id'),
            {'name': name, 'id': row.id},
        )
    op.alter_column('actions', 'name', nullable=False)
    op.create_check_constraint(
        op.f('ck_actions_name_not_blank'), 'actions', "btrim(name) <> ''"
    )
    op.create_unique_constraint('uq_actions_module_id_name', 'actions', ['module_id', 'name'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_actions_module_id_name', 'actions', type_='unique')
    op.drop_constraint(op.f('ck_actions_name_not_blank'), 'actions', type_='check')
    op.drop_column('actions', 'name')
