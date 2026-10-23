"""Registro unico de modelos para Alembic (autogenerate) y los tests.

Registrar un modulo nuevo = importar su `models.py` aqui.
"""

from app.core.db import rate_limit_model  # noqa: F401
from app.core.db.base import Base
from app.modules.applications import models as applications_models  # noqa: F401
from app.modules.audit import models as audit_models  # noqa: F401
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.roles import models as roles_models  # noqa: F401
from app.modules.users import models as users_models  # noqa: F401

__all__ = ["Base"]
