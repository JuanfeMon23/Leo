"""Engine async y sesion por request.

`get_session` es la unica dependencia FastAPI que abre/cierra sesion de BD
(una sesion por request); los tests la reemplazan por una sesion dentro de
una transaccion que se revierte (`app/conftest.py`).
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)

SessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Dependencia FastAPI: una sesion async por request."""
    async with SessionLocal() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
