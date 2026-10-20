"""Dependencias HTTP de `auth`: cookie SSO, prueba DPoP de la peticion y el
resolvedor de `Principal` que `app/main.py` conecta a `core.authz`."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.authz import Principal
from app.core.config import get_settings
from app.core.dpop import (
    DPOP_HEADER,
    DpopError,
    DpopProof,
    replay_cache,
    verify_dpop_proof,
)
from app.core.exceptions import UnauthorizedError
from app.core.request_meta import request_meta
from app.modules.auth import controller

DPOP_CHALLENGE = 'DPoP error="invalid_dpop_proof", algs="ES256"'


def session_cookie_name() -> str:
    """`__Host-` exige Secure, Path=/ y sin Domain: con HTTPS el navegador
    no deja que un subdominio la pise."""
    return "__Host-leo_session" if get_settings().leo_cookie_secure else "leo_session"


def expected_htu(request: Request) -> str:
    """`htu` esperado: URL publica configurada + path (sin query ni
    fragmento), para no depender de lo que diga un proxy."""
    return get_settings().leo_public_url.rstrip("/") + request.url.path


def verify_request_dpop(request: Request) -> DpopProof:
    proofs = request.headers.getlist(DPOP_HEADER)
    try:
        if len(proofs) > 1:
            raise DpopError("mas de un header DPoP")
        return verify_dpop_proof(
            proofs[0] if proofs else None,
            htm=request.method,
            htu=expected_htu(request),
            now=clock.now(),
            cache=replay_cache,
        )
    except DpopError as exc:
        raise UnauthorizedError(
            "Falta la prueba de posesión del dispositivo (DPoP) o no es válida. "
            "Recarga la página e intenta de nuevo.",
            code="invalid_dpop_proof",
            www_authenticate=DPOP_CHALLENGE,
        ) from exc


RequestDpop = Annotated[DpopProof, Depends(verify_request_dpop)]


async def resolve_principal(request: Request, session: AsyncSession) -> Principal:
    """Hook de `core.authz`: cookie SSO + DPoP con el jkt de la sesion."""
    cookie = request.cookies.get(session_cookie_name())
    if not cookie:
        raise UnauthorizedError()
    proof = verify_request_dpop(request)
    return await controller.authenticate_sso(
        session, cookie, proof.jkt, request_meta(request)
    )
