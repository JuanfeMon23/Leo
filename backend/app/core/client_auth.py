"""Autenticacion de clientes (backends de las apps) con client credentials
por HTTP Basic (`client_id:client_secret`, RFC 6749 `client_secret_basic`).

Igual que `authz`, el nucleo no sabe donde viven las apps: `app/main.py`
conecta el autenticador del modulo `applications` con
`configure_client_auth(...)`. Las rutas usan `AuthenticatedClient`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionDep
from app.core.exceptions import UnauthorizedError

CLIENT_AUTH_CHALLENGE = 'Basic realm="leo"'


@dataclass(frozen=True)
class ClientApp:
    """App cliente autenticada (activa)."""

    id: UUID
    slug: str
    client_id: str


ClientAuthenticator = Callable[[AsyncSession, str, str], Awaitable[ClientApp | None]]


@dataclass
class _ClientAuthConfig:
    authenticator: ClientAuthenticator | None = None


_config = _ClientAuthConfig()


def configure_client_auth(authenticator: ClientAuthenticator) -> None:
    _config.authenticator = authenticator


def invalid_client() -> UnauthorizedError:
    return UnauthorizedError(
        "Credenciales de la aplicación inválidas.",
        code="invalid_client",
        www_authenticate=CLIENT_AUTH_CHALLENGE,
    )


_basic = HTTPBasic(auto_error=False, description="client_id:client_secret")


async def authenticated_client(
    session: SessionDep,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)],
) -> ClientApp:
    if _config.authenticator is None:
        raise RuntimeError("configure_client_auth() no fue llamado al arrancar")
    if credentials is None:
        raise invalid_client()
    client = await _config.authenticator(
        session, credentials.username, credentials.password
    )
    if client is None:
        raise invalid_client()
    return client


AuthenticatedClient = Annotated[ClientApp, Depends(authenticated_client)]
