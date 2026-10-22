"""Autorizacion de endpoints de Leo que llaman OTRAS APPS con credencial de
servicio (OAuth client credentials, audiencia `leo`).

Igual que `authz`, el nucleo no sabe donde viven los tokens de servicio ni
la auditoria: `app/main.py` conecta `configure_service_authz(resolver=...,
on_denied=...)`.

- `require_service_actor(tag)`: `Depends` que exige `Authorization: Bearer
  <token de servicio>` con la audiencia `leo` y el permiso `tag` (concedido
  por un rol de Leo asignado a la app llamadora). Entrega el `Actor` de
  auditoria (actor = servicio) junto con el `ServicePrincipal`.
- Un Bearer ausente, desconocido, vencido o revocado: 401 `invalid_token`
  con `WWW-Authenticate: Bearer`. Nunca se cae a la cookie de sesion.
- Falta el permiso: 403 `forbidden` y evento de auditoria `denied`.
- Solo se aceptan permisos registrados en el catalogo de Leo, no de evento.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor
from app.core.authz import _check_permission_tag
from app.core.database import SessionDep
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.request_meta import RequestMeta, request_meta

BEARER_CHALLENGE = "Bearer"
SERVICE_ACTOR_PREFIX = "servicio:"


@dataclass(frozen=True)
class ServicePrincipal:
    """App llamadora autenticada con un token de servicio de audiencia Leo."""

    application_id: UUID
    client_id: str
    permissions: frozenset[str]

    @property
    def actor_name(self) -> str:
        return f"{SERVICE_ACTOR_PREFIX}{self.client_id}"[:64]


ServiceResolver = Callable[[AsyncSession, str], Awaitable[ServicePrincipal | None]]
ServiceDeniedRecorder = Callable[
    [AsyncSession, ServicePrincipal, str, RequestMeta], Awaitable[None]
]


@dataclass
class _Config:
    resolver: ServiceResolver | None = None
    on_denied: ServiceDeniedRecorder | None = None


_config = _Config()


def configure_service_authz(
    *, resolver: ServiceResolver, on_denied: ServiceDeniedRecorder
) -> None:
    _config.resolver = resolver
    _config.on_denied = on_denied


def invalid_token() -> UnauthorizedError:
    return UnauthorizedError(
        "Token de servicio inválido o vencido.",
        code="invalid_token",
        www_authenticate=BEARER_CHALLENGE,
    )


def _bearer(request: Request) -> str:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise invalid_token()
    return value.strip()


def require_service_actor(tag: str):
    _check_permission_tag(tag)

    async def dependency(
        request: Request,
        session: SessionDep,
        meta: Annotated[RequestMeta, Depends(request_meta)],
    ) -> tuple[ServicePrincipal, Actor]:
        if _config.resolver is None:
            raise RuntimeError("configure_service_authz() no fue llamado al arrancar")
        principal = await _config.resolver(session, _bearer(request))
        if principal is None:
            raise invalid_token()
        if tag not in principal.permissions:
            if _config.on_denied is not None:
                await _config.on_denied(session, principal, tag, meta)
            raise ForbiddenError(
                "No tienes permiso para realizar esta acción.", {"action_tag": tag}
            )
        return principal, Actor(
            user_id=None, username=principal.actor_name, session_id=None, meta=meta
        )

    dependency.__name__ = f"require_service_{tag.replace('.', '_').replace('-', '_')}"
    return Depends(dependency)


ServiceCaller = tuple[ServicePrincipal, Actor]
