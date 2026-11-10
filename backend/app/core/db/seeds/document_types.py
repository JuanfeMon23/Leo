"""Semilla del catalogo `document_types`: insert-if-missing por `code`. No
pisa nombre, orden ni `is_active` editados despues por un administrador."""

from sqlalchemy import Connection
from sqlalchemy.dialects.postgresql import insert

from app.core.db.seeds.catalog import DOCUMENT_TYPES
from app.modules.users.models import DocumentType


def seed_document_types(conn: Connection) -> None:
    table = DocumentType.__table__
    conn.execute(
        insert(table)
        .values(
            [
                {"code": code, "name": name, "sort_order": sort_order}
                for code, name, sort_order in DOCUMENT_TYPES
            ]
        )
        .on_conflict_do_nothing(index_elements=["code"])
    )
