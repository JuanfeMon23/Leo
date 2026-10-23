"""Errores de dominio del modulo de ajustes.

Cada uno lleva `status_code`, `code`, `message` (espanol, legible) y
`details`; el router los responde como `{code, message, details}`.
"""

from typing import Any, ClassVar


class SettingsError(Exception):
    status_code: int = 400
    code: str = "settings_error"

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def body(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class UnknownSettingError(SettingsError, KeyError):
    """Clave que la app no declaro en su registro (error de programacion)."""

    status_code = 404
    code = "setting_not_found"

    def __str__(self) -> str:
        return self.message


class SettingNotFoundError(SettingsError):
    status_code = 404
    code = "setting_not_found"

    def __init__(self, key: str) -> None:
        super().__init__(f"No existe el ajuste «{key}».", {"key": key})


class SettingTypeMismatchError(SettingsError):
    status_code = 422
    code = "setting_type_mismatch"

    _LABELS: ClassVar[dict[str, str]] = {
        "int": "un número entero",
        "float": "un número",
        "bool": "verdadero o falso",
        "str": "un texto",
    }

    def __init__(self, key: str, expected: str) -> None:
        super().__init__(
            f"El ajuste «{key}» debe ser {self._LABELS.get(expected, expected)}.",
            {"key": key, "expected_type": expected},
        )


class SettingOutOfRangeError(SettingsError):
    status_code = 422
    code = "setting_out_of_range"

    def __init__(
        self,
        key: str,
        value: Any,
        minimum: float | None,
        maximum: float | None,
        unit: str | None = None,
    ) -> None:
        suffix = f" {unit}" if unit else ""
        if minimum is not None and maximum is not None:
            rango = f"entre {minimum} y {maximum}{suffix}"
        elif minimum is not None:
            rango = f"al menos {minimum}{suffix}"
        else:
            rango = f"como máximo {maximum}{suffix}"
        super().__init__(
            f"El valor de «{key}» debe estar {rango}.",
            {"key": key, "value": value, "min": minimum, "max": maximum},
        )


class SettingInvalidValueError(SettingsError):
    """La BD rechazo el dato (CHECK 23514 o texto demasiado largo 22001)."""

    status_code = 422
    code = "setting_invalid_value"


class VersionConflictError(SettingsError):
    status_code = 409
    code = "version_conflict"

    def __init__(self, key: str, expected: int, current: int) -> None:
        super().__init__(
            f"El ajuste «{key}» fue modificado por otra persona. "
            "Recarga la pantalla para ver el valor vigente.",
            {"key": key, "expected_version": expected, "current_version": current},
        )


class ReasonRequiredError(SettingsError):
    status_code = 422
    code = "reason_required"

    def __init__(self, minimum: int, maximum: int) -> None:
        super().__init__(
            f"Indica el motivo del cambio ({minimum} a {maximum} caracteres).",
            {"min_length": minimum, "max_length": maximum},
        )


class SettingsUnavailableError(SettingsError):
    status_code = 503
    code = "settings_unavailable"

    def __init__(self) -> None:
        super().__init__(
            "No se pudieron consultar los ajustes. Intenta de nuevo más tarde."
        )
