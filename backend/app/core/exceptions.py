"""Errores base y handlers globales.

Los `controller.py` lanzan subclases de `AppError` (nunca `HTTPException`:
el controller no conoce HTTP). El nucleo las traduce al formato uniforme
`ErrorResponse` con mensajes en espanol. Tambien traduce:

- errores de validacion de FastAPI/Pydantic -> 422 `validation_error` con
  `details: [{field, message}]` en espanol;
- errores de la BD por SQLSTATE: 23505 (unico) -> 409 `duplicate`, 23503
  (FK) -> 422 `invalid_reference`, 23514 (CHECK) -> 422 `validation_error`,
  `LEO01` (append-only) -> 409 `append_only`;
- cualquier otra excepcion -> 500 `internal_error` sin filtrar detalles.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.core.db.triggers import APPEND_ONLY_SQLSTATE
from app.core.schemas import ErrorResponse

logger = logging.getLogger("leo")


class AppError(Exception):
    """Excepcion base de negocio. No se lanza directamente, se subclasea."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "app_error"

    def __init__(
        self,
        message: str,
        details: dict | list | str | None = None,
        *,
        code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message
        self.details = details
        self.headers = headers
        if code is not None:
            self.code = code
        super().__init__(message)


class BadRequestError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid_request"


class UnauthorizedError(AppError):
    """401. `www_authenticate` va en el header `WWW-Authenticate`."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "not_authenticated"

    def __init__(
        self,
        message: str = "Inicia sesión para continuar.",
        *,
        code: str | None = None,
        www_authenticate: str = "DPoP",
        details: dict | list | str | None = None,
    ) -> None:
        super().__init__(
            message,
            details,
            code=code,
            headers={"WWW-Authenticate": www_authenticate},
        )


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


def not_found(subject: str, entity_id: object) -> NotFoundError:
    """404 "No existe {subject} con id '{id}'." (`subject` con articulo
    indefinido: "un usuario", "una aplicacion")."""
    return NotFoundError(
        f"No existe {subject} con id '{entity_id}'.", {"id": str(entity_id)}
    )


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class DuplicateValueError(ConflictError):
    """`Ya existe {entity} con {field_label} «{value}».`; `details` lleva el
    nombre tecnico del campo para ubicar el error en el formulario."""

    code = "duplicate"

    def __init__(
        self, *, entity: str, field: str, field_label: str, value: str
    ) -> None:
        super().__init__(
            f"Ya existe {entity} con {field_label} «{value}».", {field: value}
        )


class ValidationAppError(AppError):
    """Regla de negocio invalida (distinta de la validacion de schema)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"


class TooManyRequestsError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "too_many_attempts"

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(
            message,
            {"retry_after_seconds": retry_after_seconds},
            headers={"Retry-After": str(max(1, retry_after_seconds))},
        )


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, details=details)
    return JSONResponse(
        status_code=status_code, content=body.model_dump(), headers=headers
    )


def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        exc.status_code, exc.code, exc.message, exc.details, exc.headers
    )


# Traduccion de los errores mas comunes de Pydantic a espanol. Los
# `ValueError` de validadores propios ya traen el mensaje en espanol.
_PYDANTIC_MESSAGES: dict[str, str] = {
    "missing": "Este campo es obligatorio.",
    "extra_forbidden": "Este campo no está permitido.",
    "string_too_short": "Es demasiado corto (mínimo {min_length} caracteres).",
    "string_too_long": "Es demasiado largo (máximo {max_length} caracteres).",
    "string_pattern_mismatch": "No tiene el formato esperado.",
    "string_type": "Debe ser un texto.",
    "int_parsing": "Debe ser un número entero.",
    "int_type": "Debe ser un número entero.",
    "bool_parsing": "Debe ser verdadero o falso.",
    "uuid_parsing": "Debe ser un identificador (UUID) válido.",
    "uuid_type": "Debe ser un identificador (UUID) válido.",
    "datetime_parsing": "Debe ser una fecha y hora válida (ISO 8601).",
    "datetime_from_date_parsing": "Debe ser una fecha y hora válida (ISO 8601).",
    "enum": "Debe ser uno de: {expected}.",
    "literal_error": "Debe ser uno de: {expected}.",
    "greater_than_equal": "Debe ser mayor o igual a {ge}.",
    "less_than_equal": "Debe ser menor o igual a {le}.",
    "greater_than": "Debe ser mayor que {gt}.",
    "list_type": "Debe ser una lista.",
    "too_short": "Debe tener al menos {min_length} elementos.",
    "too_long": "Debe tener como máximo {max_length} elementos.",
    "dict_type": "Debe ser un objeto.",
    "model_attributes_type": "Debe ser un objeto.",
    "json_invalid": "El cuerpo no es JSON válido.",
    "url_parsing": "Debe ser una URL válida.",
    "url_scheme": "Debe ser una URL http o https.",
    "value_error": "{error}",
    "assertion_error": "{error}",
}


def _field_message(error: dict[str, Any]) -> str:
    template = _PYDANTIC_MESSAGES.get(error.get("type", ""))
    if template is None:
        return error.get("msg", "Valor inválido.")
    ctx = {k: str(v) for k, v in (error.get("ctx") or {}).items()}
    try:
        return template.format(**ctx)
    except KeyError:
        return error.get("msg", "Valor inválido.")


def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for error in exc.errors():
        loc = [str(p) for p in error.get("loc", ()) if p not in ("body",)]
        details.append({"field": ".".join(loc), "message": _field_message(error)})
    first = details[0] if details else None
    summary = "Hay datos inválidos en la solicitud."
    if first:
        summary = (
            f"Hay datos inválidos en la solicitud: {first['field']}: {first['message']}"
        )
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", summary, details
    )


def _db_error_attr(exc: DBAPIError, attr: str) -> str | None:
    """Atributo del error de asyncpg envuelto por SQLAlchemy."""
    orig = exc.orig
    return getattr(orig, attr, None) or getattr(
        getattr(orig, "__cause__", None), attr, None
    )


def _db_error_handler(_request: Request, exc: DBAPIError) -> JSONResponse:
    sqlstate = _db_error_attr(exc, "sqlstate")
    constraint = _db_error_attr(exc, "constraint_name")
    details = {"constraint": constraint} if constraint else None
    if sqlstate == "23505":
        return _error_response(
            409,
            "duplicate",
            "Ya existe un registro con esos datos; deben ser únicos.",
            details,
        )
    if sqlstate == "23503":
        return _error_response(
            422,
            "invalid_reference",
            "Uno de los datos referenciados no existe o no corresponde "
            "(p. ej. una acción de otra aplicación).",
            details,
        )
    if sqlstate == "23514":
        return _error_response(
            422,
            "validation_error",
            "Uno de los datos no cumple el formato o las reglas permitidas.",
            details,
        )
    if sqlstate == APPEND_ONLY_SQLSTATE:
        return _error_response(
            409,
            "append_only",
            "La auditoría no se puede modificar ni borrar.",
            None,
        )
    logger.exception("Error de base de datos no mapeado (SQLSTATE %s)", sqlstate)
    return _internal_error()


def _internal_error() -> JSONResponse:
    return _error_response(
        500,
        "internal_error",
        "Ocurrió un error inesperado. Intenta de nuevo; si persiste, avisa al "
        "administrador.",
    )


def _unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Error no controlado", exc_info=exc)
    return _internal_error()


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DBAPIError, _db_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)
