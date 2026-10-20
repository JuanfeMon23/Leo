"""Fixtures de la prueba E2E contra la app REAL de Leo (`app.main:app`).

Leo se importa SOLO desde estos tests (el SDK no depende de `backend/`): se
anade `backend/` al `sys.path`. Corre contra la BD `leo_test` (la deriva el
backend de `DATABASE_URL`, que se lee de `backend/.env` o del entorno; nunca
se toca la BD de desarrollo ni se usan credenciales del admin real). Los
usuarios se crean en la BD de pruebas con la contrasena falsa del testkit.

Sin `backend/.env` ni `DATABASE_URL` en el entorno, estos tests se omiten.
"""

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4] / "backend"


def _database_url() -> str | None:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env_file = BACKEND / ".env"
    if not env_file.exists():
        return None
    from dotenv import dotenv_values

    return dotenv_values(env_file).get("DATABASE_URL")


_DSN = _database_url()
if _DSN is None or not (BACKEND / "app" / "main.py").exists():
    collect_ignore_glob = ["test_*.py"]
else:
    os.environ["DATABASE_URL"] = _DSN
    sys.path.insert(0, str(BACKEND))
    # Fixtures del backend (BD de pruebas, semilla `leo`, navegadores DPoP).
    from app.conftest import (  # noqa: F401
        _reset_process_state,
        admin,
        api_engine,
        browser,
        client,
        login_as,
        make_browser,
        migrated,
        session,
    )
