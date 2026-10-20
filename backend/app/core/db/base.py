"""Base declarativa y convencion de nombres compartida por todos los modulos.

Todo `models.py` hereda de `Base` para que sus tablas queden en el mismo
`MetaData` y Alembic mantenga una sola cadena de migraciones.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Nombres deterministas de restricciones (Alembic los usa al autogenerar y
# las migraciones pueden referenciarlas por nombre).
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ix": "ix_%(column_0_label)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    """Declarative base unica para todo el esquema de Leo."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
