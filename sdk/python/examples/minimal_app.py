"""Backend FastAPI minimo integrado con Leo.

Entorno requerido (ver README): LEO_URL, LEO_API_URL, APP_CLIENT_ID,
APP_CLIENT_SECRET, PUBLIC_URL. Ejecutar:

    uv run uvicorn examples.minimal_app:app --port 8200
"""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI

from leo_sdk import Catalog, LeoAuth, LeoSettings, LeoUser, leo_router

settings = LeoSettings()  # lee el entorno / .env
slug = settings.app_client_id

# Modulos y acciones de la app, con nombre legible (se publican en Leo).
catalog = Catalog(slug)
catalog.module("things", "Cosas", "Gestión de cosas")
catalog.action("things", "view", "Ver cosas")
catalog.action("things", "edit", "Editar cosas")

auth = LeoAuth(settings, catalog=catalog)

CanView = Annotated[LeoUser, auth.require_action(f"{slug}.things.view")]
CanEdit = Annotated[LeoUser, auth.require_action(f"{slug}.things.edit")]
THINGS: dict[int, dict] = {1: {"name": "primera", "secret_note": "no auditar"}}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    auth.check_catalog()  # falla si un require_action usa un tag no declarado
    await auth.sync_catalog()  # publica módulos y acciones en Leo
    yield
    await auth.aclose()


app = FastAPI(lifespan=lifespan)
auth.install(app)  # errores {code, message, details} y borrado de cookies
app.include_router(leo_router(auth))  # /auth/login /callback /me /activity /logout


@app.get("/things/{thing_id}")
async def read_thing(thing_id: int, user: CanView) -> dict:
    return THINGS[thing_id] | {"viewed_by": user.username}


@app.patch("/things/{thing_id}")
async def edit_thing(thing_id: int, name: str, user: CanEdit) -> dict:
    before = dict(THINGS[thing_id])
    THINGS[thing_id]["name"] = name
    await auth.audit.record(
        f"{slug}.things.edit",
        entity_type="thing",
        entity_id=str(thing_id),
        changes=auth.audit.diff(before, THINGS[thing_id]),
        actor=user,
    )
    return THINGS[thing_id]
