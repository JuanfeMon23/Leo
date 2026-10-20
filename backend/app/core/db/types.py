"""Tipos de columna reutilizables."""

import enum

from sqlalchemy import Enum


def str_enum(enum_cls: type[enum.StrEnum], name: str, length: int) -> Enum:
    """Enum como `varchar(length)` + CHECK `ck_<tabla>_<name>` (no tipo nativo
    de PostgreSQL), con los `value` del `StrEnum` como valores permitidos."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        create_constraint=True,
        name=name,
    )
