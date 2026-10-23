"""Ajustes editables en caliente, reutilizables por todas las apps.

Requiere el extra opcional: `pip install "leo-sdk[settings]"` (SQLAlchemy
async + FastAPI). No se importa desde `leo_sdk`, asi que la instalacion base
no lo necesita.

Piezas:
- `SettingDef` / `SettingsRegistry`: la app declara sus claves en codigo.
- `make_settings_models(Base)`: tablas `settings` y `settings_history`.
- `migration.upgrade(op)` / `migration.downgrade(op)`: para la migracion
  Alembic de cada app.
- `SettingsStore`: lectura tipada con cache, `update` con historial,
  `sync_registry` al arrancar.
- `build_settings_router(store, deps)`: API de la pantalla Ajustes.
"""

from leo_sdk.settings_store.definitions import (
    KEY_PATTERN,
    SettingDef,
    SettingsRegistry,
)
from leo_sdk.settings_store.errors import (
    ReasonRequiredError,
    SettingInvalidValueError,
    SettingNotFoundError,
    SettingOutOfRangeError,
    SettingsError,
    SettingsUnavailableError,
    SettingTypeMismatchError,
    UnknownSettingError,
    VersionConflictError,
)
from leo_sdk.settings_store.router import (
    SettingsRouterDeps,
    build_settings_router,
    default_actor,
)
from leo_sdk.settings_store.schema import SettingsModels, make_settings_models
from leo_sdk.settings_store.store import (
    SYSTEM_ACTOR,
    HistoryEntry,
    HistoryPage,
    SettingChange,
    SettingsActor,
    SettingsStore,
    SettingView,
    SyncResult,
)

__all__ = [
    "KEY_PATTERN",
    "SYSTEM_ACTOR",
    "HistoryEntry",
    "HistoryPage",
    "ReasonRequiredError",
    "SettingChange",
    "SettingDef",
    "SettingInvalidValueError",
    "SettingNotFoundError",
    "SettingOutOfRangeError",
    "SettingTypeMismatchError",
    "SettingView",
    "SettingsActor",
    "SettingsError",
    "SettingsModels",
    "SettingsRegistry",
    "SettingsRouterDeps",
    "SettingsStore",
    "SettingsUnavailableError",
    "SyncResult",
    "UnknownSettingError",
    "VersionConflictError",
    "build_settings_router",
    "default_actor",
    "make_settings_models",
]
