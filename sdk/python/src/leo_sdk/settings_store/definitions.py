"""Definiciones de ajustes (en codigo) y su registro. Sin dependencias de BD."""

import math
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Literal

from leo_sdk.settings_store.errors import (
    SettingOutOfRangeError,
    SettingTypeMismatchError,
    UnknownSettingError,
)

SettingType = Literal["int", "float", "bool", "str"]
SETTING_TYPES: tuple[str, ...] = ("int", "float", "bool", "str")
# Mismo patron que el CHECK `ck_settings_key_format` de la BD.
KEY_PATTERN = r"^[a-z0-9_]+(\.[a-z0-9_]+)+$"
_KEY_RE = re.compile(KEY_PATTERN)
KEY_MAX_LENGTH = 100
GROUP_MAX_LENGTH = 40
UNIT_MAX_LENGTH = 16


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


@dataclass(frozen=True)
class SettingDef:
    """Un ajuste declarado por la app.

    `min`/`max` solo para `int`/`float` (inclusivos). `requires_security`:
    editarlo exige el permiso de seguridad ademas del de edicion. `group`
    vacio = primer segmento de la clave.
    """

    key: str
    type: SettingType
    default: Any
    description: str
    min: int | float | None = None
    max: int | float | None = None
    unit: str | None = None
    group: str = ""
    requires_security: bool = False

    def __post_init__(self) -> None:
        if len(self.key) > KEY_MAX_LENGTH or not _KEY_RE.match(self.key):
            raise ValueError(
                f"Clave de ajuste inválida {self.key!r}: debe cumplir {KEY_PATTERN}"
                f" y tener máximo {KEY_MAX_LENGTH} caracteres."
            )
        if self.type not in SETTING_TYPES:
            raise ValueError(f"{self.key}: tipo inválido {self.type!r}.")
        group = self.group or self.key.split(".", 1)[0]
        object.__setattr__(self, "group", group)
        if not group.strip() or len(group) > GROUP_MAX_LENGTH:
            raise ValueError(f"{self.key}: grupo vacío o de más de 40 caracteres.")
        if self.unit is not None and (
            not self.unit or len(self.unit) > UNIT_MAX_LENGTH
        ):
            raise ValueError(f"{self.key}: unidad vacía o de más de 16 caracteres.")
        if not self.description.strip():
            raise ValueError(f"{self.key}: la descripción es obligatoria.")
        numeric = self.type in ("int", "float")
        if not numeric and (self.min is not None or self.max is not None):
            raise ValueError(f"{self.key}: min/max solo aplican a int/float.")
        for name in ("min", "max"):
            bound = getattr(self, name)
            if bound is None:
                continue
            if not _is_number(bound) or (self.type == "int" and not _is_int(bound)):
                raise ValueError(f"{self.key}: {name} no es válido para {self.type}.")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"{self.key}: min es mayor que max.")
        try:
            default = self.coerce(self.default)
        except (SettingTypeMismatchError, SettingOutOfRangeError) as exc:
            raise ValueError(
                f"{self.key}: el valor por defecto no es válido: {exc.message}"
            ) from exc
        object.__setattr__(self, "default", default)

    def coerce(self, value: Any) -> Any:
        """Valor validado (y normalizado: `float` siempre como float).

        Lanza `SettingTypeMismatchError` o `SettingOutOfRangeError`."""
        if self.type == "bool":
            if not isinstance(value, bool):
                raise SettingTypeMismatchError(self.key, self.type)
            return value
        if self.type == "str":
            if not isinstance(value, str):
                raise SettingTypeMismatchError(self.key, self.type)
            return value
        if self.type == "int":
            if not _is_int(value):
                raise SettingTypeMismatchError(self.key, self.type)
        elif not _is_number(value):
            raise SettingTypeMismatchError(self.key, self.type)
        if (self.min is not None and value < self.min) or (
            self.max is not None and value > self.max
        ):
            raise SettingOutOfRangeError(self.key, value, self.min, self.max, self.unit)
        return float(value) if self.type == "float" else value

    def is_valid(self, value: Any) -> bool:
        try:
            self.coerce(value)
        except (SettingTypeMismatchError, SettingOutOfRangeError):
            return False
        return True

    def clamp(self, value: Any) -> Any:
        """`value` ajustado al rango (solo numericos)."""
        if self.min is not None and value < self.min:
            return self.min
        if self.max is not None and value > self.max:
            return self.max
        return value


class SettingsRegistry:
    """Conjunto de `SettingDef` de una app (claves unicas, orden de declaracion)."""

    def __init__(self, definitions: Iterable[SettingDef] = ()) -> None:
        self._defs: dict[str, SettingDef] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: SettingDef) -> SettingDef:
        if definition.key in self._defs:
            raise ValueError(f"Ajuste duplicado: {definition.key}.")
        self._defs[definition.key] = definition
        return definition

    def get(self, key: str) -> SettingDef:
        try:
            return self._defs[key]
        except KeyError:
            raise UnknownSettingError(
                f"El ajuste «{key}» no está declarado en el registro.", {"key": key}
            ) from None

    def __contains__(self, key: object) -> bool:
        return key in self._defs

    def __iter__(self) -> Iterator[SettingDef]:
        return iter(self._defs.values())

    def __len__(self) -> int:
        return len(self._defs)

    def keys(self) -> list[str]:
        return list(self._defs)
