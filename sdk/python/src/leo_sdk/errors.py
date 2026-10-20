"""Errores legibles y tipados del SDK.

`LeoError` lleva `code` y `message` del backend de Leo (formato
`{code, message, details}`, mensajes en espanol listos para el usuario) o los
propios del BFF. `status_code` es el HTTP con que el BFF lo responde.
"""

from typing import Any


class LeoError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any = None,
        *,
        clear_cookies: bool = False,
        www_authenticate: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        # El BFF borra las cookies de sesion al responder este error.
        self.clear_cookies = clear_cookies
        # Valor de `WWW-Authenticate` de la respuesta 401 (opcional).
        self.www_authenticate = www_authenticate

    def body(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.code!r}, {self.message!r}, {self.status_code})"


class InvalidClientError(LeoError):
    """401 `invalid_client`: client_id/client_secret de la app rechazados."""


class InvalidGrantError(LeoError):
    """400 `invalid_grant`: code/refresh invalido, usado, vencido o de otro jkt."""


class InvalidTargetError(LeoError):
    """400 `invalid_target`: la audiencia no existe o no esta activa."""


class ServiceAccessDenied(LeoError):
    """403 `access_denied`: la app no tiene concesion hacia esa audiencia."""


class TooManyAttemptsError(LeoError):
    """429 `too_many_attempts`; `retry_after` en segundos si Leo lo indica."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 429,
        details: Any = None,
        *,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(code, message, status_code, details)
        self.retry_after = retry_after


class LeoUnavailableError(LeoError):
    """Leo no respondio o fallo (red, 5xx)."""

    def __init__(self, message: str | None = None, details: Any = None) -> None:
        super().__init__(
            "leo_unavailable",
            message
            or "No se pudo comunicar con Leo. Intenta de nuevo en unos segundos.",
            503,
            details,
        )


def error_from_response(
    status_code: int, payload: Any, *, retry_after: int | None = None
) -> LeoError:
    """Traduce el cuerpo de error de Leo al tipo correspondiente."""
    data = payload if isinstance(payload, dict) else {}
    code = str(data.get("code") or "leo_error")
    message = str(data.get("message") or "Leo rechazó la solicitud.")
    details = data.get("details")
    if status_code >= 500:
        return LeoUnavailableError(message, details)
    if code == "invalid_client" and status_code == 401:
        return InvalidClientError(code, message, status_code, details)
    if code == "invalid_target":
        return InvalidTargetError(code, message, status_code, details)
    if code == "access_denied" and status_code == 403:
        return ServiceAccessDenied(code, message, status_code, details)
    if code == "too_many_attempts" or status_code == 429:
        return TooManyAttemptsError(
            code, message, status_code, details, retry_after=retry_after
        )
    if code == "invalid_grant":
        return InvalidGrantError(code, message, status_code, details)
    return LeoError(code, message, status_code, details)
