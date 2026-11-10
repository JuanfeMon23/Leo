"""document_types: catalogo de tipos de documento (reemplaza el CHECK)

Catalogos en BD (2026-11-09). Leo es dueno unico de los tipos de documento;
las demas apps los consumen por su API. `users.document_type` pasa de CHECK con
tupla a FK al `code` del catalogo. La semilla copia los 8 codigos vigentes
(copia, no import: la migracion es inmutable aunque cambie el catalogo vivo).
Downgrade: restaura el CHECK; falla con mensaje claro si hay usuarios con un
codigo fuera de los 8 originales (no se reescriben datos de personas).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-09 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DOCUMENT_TYPES = (
    ("CC", "Cédula de ciudadanía", 10),
    ("CE", "Cédula de extranjería", 20),
    ("TI", "Tarjeta de identidad", 30),
    ("RC", "Registro civil", 40),
    ("PA", "Pasaporte", 50),
    ("NIT", "NIT", 60),
    ("PEP", "Permiso especial de permanencia", 70),
    ("PPT", "Permiso por protección temporal", 80),
)
_CODES = tuple(code for code, _name, _order in _DOCUMENT_TYPES)
_OLD_CHECK = "document_type IN (" + ", ".join(f"'{c}'" for c in _CODES) + ")"


def upgrade() -> None:
    """Upgrade schema."""
    table = op.create_table(
        "document_types",
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name=op.f("ck_document_types_name_not_blank")
        ),
        sa.CheckConstraint(
            "code ~ '^[A-Z][A-Z0-9]*$'", name=op.f("ck_document_types_code_format")
        ),
        sa.CheckConstraint(
            "sort_order >= 0", name=op.f("ck_document_types_sort_order_non_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_types")),
        sa.UniqueConstraint("code", name=op.f("uq_document_types_code")),
    )
    op.bulk_insert(
        table,
        [
            {"code": code, "name": name, "sort_order": order}
            for code, name, order in _DOCUMENT_TYPES
        ],
    )
    op.create_foreign_key(
        op.f("fk_users_document_type_document_types"),
        "users",
        "document_types",
        ["document_type"],
        ["code"],
    )
    op.drop_constraint(op.f("ck_users_document_type"), "users", type_="check")


def downgrade() -> None:
    """Downgrade schema."""
    outside = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM users WHERE document_type <> ALL(:codes)"
            ).bindparams(
                sa.bindparam("codes", value=list(_CODES), type_=sa.ARRAY(sa.String))
            )
        )
        .scalar_one()
    )
    if outside:
        raise RuntimeError(
            f"{outside} usuario(s) usan un tipo de documento fuera de "
            f"{', '.join(_CODES)}; reasignalos antes de bajar 0009."
        )
    op.create_check_constraint(op.f("ck_users_document_type"), "users", _OLD_CHECK)
    op.drop_constraint(
        op.f("fk_users_document_type_document_types"), "users", type_="foreignkey"
    )
    op.drop_table("document_types")
