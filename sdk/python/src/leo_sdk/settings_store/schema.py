"""Modelos SQLAlchemy reutilizables de `settings` y `settings_history`.

`make_settings_models(Base)` declara ambas tablas sobre la `Base` de la app
con los mismos nombres de tabla, columnas, restricciones e indices en todas
las apps (los nombres de constraints son explicitos, no dependen de la
convencion de nombres de la `Base`).

- `settings`: catalogo + valor vigente (una fila por clave). `value_type`
  fija el tipo del JSON; `min_value`/`max_value` acotan int/float. Los CHECK
  garantizan tipo y rango en la BD. `version` sube en cada cambio (bloqueo
  optimista). `updated_by` referencia a la tabla de usuarios de la app (sin
  ON DELETE: los usuarios se desactivan, no se borran); `updated_by_username`
  es el snapshot.
- `settings_history`: append-only (trigger, ver `migration`). `setting_key`
  NO tiene FK a proposito: el historial sobrevive a cambios del catalogo.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.elements import conv

from leo_sdk.settings_store.definitions import KEY_PATTERN

SETTINGS_TABLE = "settings"
HISTORY_TABLE = "settings_history"

_NUM = "(({col}) #>> '{{}}')::numeric"
_IS_NUM = "jsonb_typeof({col}) = 'number'"
_NUM_OR_NULL = "({col} IS NULL OR jsonb_typeof({col}) = 'number')"


def _numeric_typed(int_only: bool) -> str:
    # El texto de un jsonb numerico entero no lleva punto ni exponente.
    parts = [
        _IS_NUM.format(col="value"),
        _IS_NUM.format(col="default_value"),
        _NUM_OR_NULL.format(col="min_value"),
        _NUM_OR_NULL.format(col="max_value"),
    ]
    if int_only:
        for col in ("value", "default_value", "min_value", "max_value"):
            parts.append(f"({col} IS NULL OR ({col} #>> '{{}}') ~ '^-?[0-9]+$')")
    return " AND ".join(parts)


TYPED_VALUES_SQL = (
    "CASE value_type "
    f"WHEN 'int' THEN {_numeric_typed(True)} "
    f"WHEN 'float' THEN {_numeric_typed(False)} "
    "WHEN 'bool' THEN jsonb_typeof(value) = 'boolean' "
    "AND jsonb_typeof(default_value) = 'boolean' "
    "AND min_value IS NULL AND max_value IS NULL "
    "WHEN 'str' THEN jsonb_typeof(value) = 'string' "
    "AND jsonb_typeof(default_value) = 'string' "
    "AND min_value IS NULL AND max_value IS NULL "
    "ELSE false END"
)

# Solo evalua los casts cuando ya se sabe que los jsonb son numericos (CASE
# garantiza el orden; un AND no).
VALUE_IN_RANGE_SQL = (
    "CASE WHEN value_type IN ('int', 'float') "
    f"AND {_IS_NUM.format(col='value')} AND {_IS_NUM.format(col='default_value')} "
    f"AND {_NUM_OR_NULL.format(col='min_value')} "
    f"AND {_NUM_OR_NULL.format(col='max_value')} "
    f"THEN (min_value IS NULL OR {_NUM.format(col='min_value')} "
    f"<= {_NUM.format(col='value')} "
    f"AND {_NUM.format(col='min_value')} <= {_NUM.format(col='default_value')}) "
    f"AND (max_value IS NULL OR {_NUM.format(col='value')} "
    f"<= {_NUM.format(col='max_value')} "
    f"AND {_NUM.format(col='default_value')} <= {_NUM.format(col='max_value')}) "
    "AND (min_value IS NULL OR max_value IS NULL "
    f"OR {_NUM.format(col='min_value')} <= {_NUM.format(col='max_value')}) "
    "ELSE true END"
)


@dataclass(frozen=True)
class SettingsModels:
    Setting: type
    SettingHistory: type


def _ck(sql: str, name: str) -> CheckConstraint:
    return CheckConstraint(sql, name=conv(f"ck_{SETTINGS_TABLE}_{name}"))


def make_settings_models(
    base: type[DeclarativeBase], *, user_pk: str | None = "users.id"
) -> SettingsModels:
    """Declara `Setting` y `SettingHistory` sobre `base`.

    `user_pk`: columna `tabla.columna` (UUID) de los usuarios de la app, a la
    que apuntan `updated_by` y `changed_by`. Con `user_pk=None` (apps sin tabla
    de usuarios) ambas son UUID simples, sin llave foranea.
    """
    user_table = user_pk.split(".", 1)[0] if user_pk else None

    def actor_fk(table: str, column: str) -> tuple[ForeignKey, ...]:
        if user_pk is None:
            return ()
        return (ForeignKey(user_pk, name=conv(f"fk_{table}_{column}_{user_table}")),)

    class Setting(base):  # type: ignore[valid-type, misc]
        __tablename__ = SETTINGS_TABLE
        __table_args__ = (
            PrimaryKeyConstraint("key", name=conv(f"pk_{SETTINGS_TABLE}")),
            _ck(f"key ~ '{KEY_PATTERN}'", "key_format"),
            _ck("value_type IN ('int', 'float', 'bool', 'str')", "value_type"),
            _ck(TYPED_VALUES_SQL, "typed_values"),
            _ck(VALUE_IN_RANGE_SQL, "value_in_range"),
            _ck("version >= 1", "version_positive"),
            _ck("btrim(group_name) <> ''", "group_name_not_blank"),
        )

        key: Mapped[str] = mapped_column(String(100))
        value: Mapped[Any] = mapped_column(JSONB, nullable=False)
        value_type: Mapped[str] = mapped_column(String(16), nullable=False)
        min_value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
        max_value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
        default_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
        # 'seconds', 'minutes', 'hours', 'count'... (informativo para la UI).
        unit: Mapped[str | None] = mapped_column(String(16))
        group_name: Mapped[str] = mapped_column(String(40), nullable=False)
        description: Mapped[str] = mapped_column(Text, nullable=False)
        requires_security_permission: Mapped[bool] = mapped_column(
            Boolean, server_default=text("false"), nullable=False
        )
        version: Mapped[int] = mapped_column(
            Integer, server_default=text("1"), nullable=False
        )
        updated_by: Mapped[uuid.UUID | None] = mapped_column(
            UUID(as_uuid=True), *actor_fk(SETTINGS_TABLE, "updated_by")
        )
        updated_by_username: Mapped[str | None] = mapped_column(String(100))
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
        )
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )

    class SettingHistory(base):  # type: ignore[valid-type, misc]
        __tablename__ = HISTORY_TABLE
        __table_args__ = (
            PrimaryKeyConstraint("id", name=conv(f"pk_{HISTORY_TABLE}")),
            CheckConstraint(
                "char_length(reason) >= 3",
                name=conv(f"ck_{HISTORY_TABLE}_reason_min_length"),
            ),
            CheckConstraint(
                "version_after >= 1",
                name=conv(f"ck_{HISTORY_TABLE}_version_after_positive"),
            ),
            Index(
                "ix_settings_history_setting_key_changed_at",
                "setting_key",
                text("changed_at DESC"),
            ),
        )

        id: Mapped[uuid.UUID] = mapped_column(
            UUID(as_uuid=True), server_default=text("uuidv7()")
        )
        # Sin FK: el historial sobrevive a cambios del catalogo.
        setting_key: Mapped[str] = mapped_column(String(100), nullable=False)
        old_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
        new_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
        version_after: Mapped[int] = mapped_column(Integer, nullable=False)
        changed_by: Mapped[uuid.UUID | None] = mapped_column(
            UUID(as_uuid=True), *actor_fk(HISTORY_TABLE, "changed_by")
        )
        changed_by_username: Mapped[str | None] = mapped_column(String(100))
        changed_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            server_default=func.clock_timestamp(),
            nullable=False,
        )
        reason: Mapped[str] = mapped_column(String(500), nullable=False)
        request_id: Mapped[str | None] = mapped_column(String(64))

    return SettingsModels(Setting=Setting, SettingHistory=SettingHistory)
