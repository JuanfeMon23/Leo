"""Interfaz publica del modulo `audit`.

Otros modulos solo importan lo que se expone aqui (nunca `repository`,
`models` ni `schemas` internos directamente). Para evitar ciclos, los demas
modulos lo importan como `from app.modules import audit` y llaman
`audit.record_event(...)` en tiempo de ejecucion.

- `record_event(session, entry)`: agrega un evento a la transaccion en curso.
- `record_and_commit(session, entry)`: idem y confirma (peticiones que fallan).
- `record_change(session, actor, tag, entity_type, entity, before, fields)`:
  flush + diff before/after + evento (sin commit).
- `record_denied(...)`: hook `on_denied` de `require_action`.
- `record_service_denied(...)`: idem de `require_service_actor`.
- `audit_router`: rutas `/api/v1/audit`.
"""

from app.modules.audit.controller import (
    record_and_commit,
    record_change,
    record_denied,
    record_event,
    record_service_denied,
)
from app.modules.audit.router import router as audit_router

__all__ = [
    "audit_router",
    "record_and_commit",
    "record_change",
    "record_denied",
    "record_event",
    "record_service_denied",
]
