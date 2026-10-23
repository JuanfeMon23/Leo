"""Entorno de Alembic (async, asyncpg).

La URL sale de `MIGRATION_DATABASE_URL` (rol `leo_migrator`, dueno del
esquema) si existe; si no, de `DATABASE_URL`. Primero del entorno del proceso
(los tests lo sobreescriben para apuntar a `leo_test`), si no de
`backend/.env`. Un valor vacio cuenta como ausente.
"""

import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

load_dotenv(Path(__file__).resolve().parents[1] / ".env")  # no pisa el entorno

from app.core.db.registry import Base

config = context.config

database_url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get(
    "DATABASE_URL"
)
if not database_url:
    raise RuntimeError(
        "Falta DATABASE_URL o MIGRATION_DATABASE_URL (backend/.env o entorno)."
    )
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
