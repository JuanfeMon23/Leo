"""E2E: credenciales de servicio contra la app REAL de Leo.

Una app audiencia (con un endpoint protegido por `require_action`) y una app
llamadora con una concesion de rol de la audiencia: el proveedor canjea el
token, el cliente httpx lo usa y la audiencia lo introspecciona en Leo. Quitar
la concesion corta el acceso.
"""

import logging
from collections.abc import Callable
from typing import Annotated

import httpx
import pytest
from app.testkit import (
    Browser as LeoBrowser,
)
from app.testkit import (
    grant_service_access,
    make_client_app,
    make_role,
    unique,
)
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from leo_sdk import (
    LeoAuth,
    LeoClient,
    LeoSettings,
    LeoUser,
    ServiceAccessDenied,
    ServiceTokenProvider,
)

LEO_PUBLIC = "https://leo.test"


def _settings(slug: str, secret: str) -> LeoSettings:
    return LeoSettings(
        leo_url="https://admin.leo.test",
        leo_api_url=f"{LEO_PUBLIC}/api/v1",
        app_client_id=slug,
        app_client_secret=secret,
        public_url=f"https://{slug}.test",
    )


async def test_service_calls_audience_until_grant_is_removed(
    session: AsyncSession,
    make_browser: Callable[[], LeoBrowser],
    caplog: pytest.LogCaptureFixture,
) -> None:
    aud_slug, caller_slug = unique("aud"), unique("caller")
    aud = await make_client_app(
        session, slug=aud_slug, tags=["things.view", "things.edit"]
    )
    caller = await make_client_app(session, slug=caller_slug)
    role = await make_role(session, aud.app.id, tags=[f"{aud_slug}.things.view"])
    grant = await grant_service_access(session, caller.app, role)
    await session.commit()

    leo_http = make_browser().client
    # --- audiencia (p. ej. Vladimir): acepta Bearer de servicio
    aud_settings = _settings(aud_slug, aud.secret)
    aud_auth = LeoAuth(aud_settings, client=LeoClient(aud_settings, http=leo_http))
    app = FastAPI()
    aud_auth.install(app)
    view = Annotated[LeoUser, aud_auth.require_action(f"{aud_slug}.things.view")]
    edit = Annotated[LeoUser, aud_auth.require_action(f"{aud_slug}.things.edit")]

    @app.get("/things")
    async def things(principal: view) -> dict:
        return {"type": principal.principal_type, "caller": principal.client_id}

    @app.post("/things")
    async def change(principal: edit) -> dict:
        return {"ok": True}

    # --- consumidor (p. ej. Incubus)
    caller_settings = _settings(caller_slug, caller.secret)
    provider = ServiceTokenProvider(LeoClient(caller_settings, http=leo_http))
    service_http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=f"https://{aud_slug}.test",
        auth=provider.auth(aud_slug),
    )

    ok = await service_http.get("/things")
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"type": "service", "caller": caller_slug}

    # sin permiso para editar: 403 y el evento `denied` se ingesta en Leo
    caplog.set_level(logging.ERROR, logger="leo_sdk.audit")
    denied = await service_http.post("/things")
    assert denied.status_code == 403 and denied.json()["code"] == "forbidden"
    assert aud_auth.audit.pending == 0
    assert "rechaz" not in caplog.text

    # sin Authorization no hay acceso
    assert (
        await httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=f"https://{aud_slug}.test"
        ).get("/things")
    ).status_code == 401

    # se quita la concesion: el token vigente deja de servir al expirar la
    # cache de introspeccion y no se puede canjear uno nuevo
    await session.delete(grant)
    await session.commit()
    aud_auth.sessions._cache.clear()  # equivale a esperar los 30 s de cache
    # el destino da 401, el cliente intenta renovar una vez y Leo ya no emite
    with pytest.raises(ServiceAccessDenied):
        await service_http.get("/things")
    provider.invalidate()
    with pytest.raises(ServiceAccessDenied):
        await provider.token(aud_slug)
    await service_http.aclose()
