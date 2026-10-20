"""Esquemas genericos del nucleo: error uniforme, paginacion y `responses=`.

Cualquier modulo que pagine un listado o documente errores reutiliza lo de
aqui; no se redefine por modulo (ver `CATALOG.md`).
"""

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Formato unico de error de toda la API: `message` en espanol, legible
    por el usuario final; `code` estable para que el frontend/SDK decida;
    `details` opcional (campos invalidos, ids, ...)."""

    code: str = Field(examples=["not_found"])
    message: str = Field(examples=["No existe un usuario con id '...'."])
    details: dict | list | str | None = None


class Page[T](BaseModel):
    """Respuesta paginada generica: `Page[XRead]`."""

    items: list[T]
    total: int
    page: int
    page_size: int


_ERROR_DESCRIPTIONS: dict[int, str] = {
    400: "Solicitud invalida para el protocolo (`invalid_grant`, `invalid_request`...).",
    401: (
        "Sin sesion valida (`not_authenticated`, `session_expired`, "
        "`invalid_dpop_proof`, `invalid_credentials`, `invalid_client`). "
        "Lleva `WWW-Authenticate`."
    ),
    403: "Sin permiso (`forbidden`, `access_denied`, `user_inactive`...).",
    404: "No existe el recurso (`not_found`).",
    409: "Conflicto con lo existente (`duplicate`, `conflict`, `append_only`).",
    422: (
        "Datos invalidos (`validation_error` con `details: [{field, message}]`) "
        "o regla de negocio incumplida (`weak_password`, `invalid_reference`...)."
    ),
    429: "Demasiados intentos (`too_many_attempts`). Lleva `Retry-After`.",
}


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """`responses=` de una ruta: `@router.get(..., responses=error_responses(401, 403))`."""
    return {
        status: {"model": ErrorResponse, "description": _ERROR_DESCRIPTIONS[status]}
        for status in statuses
    }


AUTH_ERRORS = (401, 403)
"""Errores de toda ruta protegida con `require_action` (sesion + permiso)."""
