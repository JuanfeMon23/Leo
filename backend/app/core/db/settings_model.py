"""Tablas `settings` y `settings_history`: politicas operativas editables por
un administrador, con historial inmutable.

El esquema es el modulo compartido `leo_sdk.settings_store` (el mismo para
todas las apps del ecosistema); Leo solo lo declara sobre su `Base`. La
migracion 0008 usa `leo_sdk.settings_store.migration`. `updated_by` y
`changed_by` referencian `users.id` (los usuarios se desactivan, no se
borran). Ver el docstring de `leo_sdk.settings_store.schema`.
"""

from leo_sdk.settings_store import make_settings_models

from app.core.db.base import Base

_models = make_settings_models(Base, user_pk="users.id")
Setting = _models.Setting
SettingHistory = _models.SettingHistory
SETTINGS_MODELS = _models
