"""Runner: `uv run python -m app.core.db.seeds` (desde `backend/`, con el
esquema en `alembic upgrade head`). Idempotente; una sola transaccion."""

import asyncio
import sys

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import SeedSettings, get_settings
from app.core.db.seeds.admin import SeedConfigError
from app.core.db.seeds.runner import run_seeds


async def main() -> int:
    settings = SeedSettings()
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            report = await conn.run_sync(lambda sync: run_seeds(sync, settings))
    except SeedConfigError as exc:
        print(f"Semilla cancelada: {exc}", file=sys.stderr)
        return 1
    except IntegrityError:
        print(
            "Semilla cancelada: ya existe otro usuario con ese email o documento "
            "(LEO_ADMIN_EMAIL / LEO_ADMIN_DOCUMENT_*).",
            file=sys.stderr,
        )
        return 1
    finally:
        await engine.dispose()
    state = "creado" if report.admin_created else "ya existia (sin cambios)"
    print(f"ok: app leo, rol leo-admin; admin '{report.admin_username}' {state}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
