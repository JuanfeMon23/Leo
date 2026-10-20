"""Autorizacion de la propia API de Leo: `require_action("leo.<modulo>.<verbo>")`.

El nucleo no conoce como se autentica una peticion ni como se escribe la
auditoria (eso es de los modulos `auth` y `audit`): `app/main.py` los
conecta al arrancar con `configure_authz(resolver=..., on_denied=...)`.

- `CurrentPrincipal`: dependencia que exige sesion valida (cookie SSO +
  DPoP) y devuelve el `Principal` con sus permisos `leo.*` efectivos.
- `require_action(tag)`: `Depends` que exige ademas el tag; si falta,
  registra un evento de auditoria `denied` (persistido aunque la peticion
  falle) y responde 403 `forbidden`. Solo acepta permisos registrados en
  el catalogo de Leo (`core/db/seeds/catalog.py`) y nunca un tag de
  **evento** (descripcion "Evento:"): esos solo se auditan.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor
from app.core.database import SessionDep
from app.core.db.seeds.catalog import LEO_APP_SLUG, LEO_MODULES
from app.core.exceptions import ForbiddenError
from app.core.request_meta import RequestMeta, request_meta


@dataclass(frozen=True)
class Principal:
    """Usuario autenticado en la API de Leo (sesion SSO)."""

    user_id: UUID
    username: str
    session_id: UUID
    permissions: frozenset[str]


PrincipalResolver = Callable[[Request, AsyncSession], Awaitable[Principal]]
DeniedRecorder = Callable[[AsyncSession, Principal, str, RequestMeta], Awaitable[None]]


@dataclass
class _AuthzConfig:
    resolver: PrincipalResolver | None = None
    on_denied: DeniedRecorder | None = None


_config = _AuthzConfig()


def configure_authz(*, resolver: PrincipalResolver, on_denied: DeniedRecorder) -> None:
    """Lo llama `app/main.py` una vez al arrancar."""
    _config.resolver = resolver
    _config.on_denied = on_denied


async def current_principal(request: Request, session: SessionDep) -> Principal:
    if _config.resolver is None:
        raise RuntimeError("configure_authz() no fue llamado al arrancar la app")
    return await _config.resolver(request, session)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


EVENT_PREFIX = "Evento:"


def _catalog_tags() -> dict[str, str]:
    return {
        f"{LEO_APP_SLUG}.{module}.{verb}": description
        for module, (_, verbs) in LEO_MODULES.items()
        for verb, description in verbs.items()
    }


def _check_permission_tag(tag: str) -> None:
    """Falla al importar el router (no en una peticion) si `tag` no es un
    permiso registrado de Leo o si es un tag de evento."""
    description = _catalog_tags().get(tag)
    if description is None:
        raise ValueError(f"El tag «{tag}» no esta registrado en el catalogo de Leo.")
    if description.startswith(EVENT_PREFIX):
        raise ValueError(
            f"El tag «{tag}» es de evento (solo auditoria); no protege endpoints."
        )


def require_action(tag: str) -> Any:
    """`Depends` que exige el permiso `tag` (uso: `dependencies=[require_action(
    "leo.users.view")]` o `principal: Annotated[Principal, require_action(...)]`)."""
    _check_permission_tag(tag)

    async def dependency(
        principal: CurrentPrincipal,
        session: SessionDep,
        meta: Annotated[RequestMeta, Depends(request_meta)],
    ) -> Principal:
        if tag in principal.permissions:
            return principal
        if _config.on_denied is not None:
            await _config.on_denied(session, principal, tag, meta)
        raise ForbiddenError(
            "No tienes permiso para realizar esta acción.", {"action_tag": tag}
        )

    dependency.__name__ = f"require_{tag.replace('.', '_').replace('-', '_')}"
    return Depends(dependency)


def require_actor(tag: str) -> Any:
    """Como `require_action`, pero entrega el `Actor` (usuario + ip,
    user-agent, request_id) que los controllers usan para auditar."""
    guard = require_action(tag)

    async def dependency(
        principal: Annotated[Principal, guard],
        meta: Annotated[RequestMeta, Depends(request_meta)],
    ) -> Actor:
        return Actor(
            user_id=principal.user_id,
            username=principal.username,
            session_id=principal.session_id,
            meta=meta,
        )

    return Depends(dependency)
