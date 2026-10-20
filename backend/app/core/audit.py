"""Piezas puras del cliente de auditoria: el evento a registrar y el diff
before/after. La escritura (INSERT en `audit_events`) la expone el modulo
`audit` en su interfaz publica (`record_event`); el nucleo no depende de el.

Regla: nunca van al diff contrasenas, hashes, secretos ni tokens (se
descartan por nombre de campo, ver `is_sensitive`).
"""

import enum
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from app.core.request_meta import RequestMeta

_SENSITIVE_PARTS = ("password", "secret", "token", "hash", "code_verifier", "jkt")


def is_sensitive(name: str) -> bool:
    lowered = name.lower()
    return any(part in lowered for part in _SENSITIVE_PARTS)


def json_safe(value: Any) -> Any:
    """Valor serializable en JSONB (uuid/fecha/enum a texto, listas/dicts
    recursivos)."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list | tuple | set | frozenset):
        items = [json_safe(v) for v in value]
        return sorted(items, key=str) if isinstance(value, set | frozenset) else items
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    return value


def snapshot(entity: Any, fields: tuple[str, ...] | list[str]) -> dict[str, Any]:
    """Estado de `entity` en esos campos (sin los sensibles), para el diff."""
    return {
        name: json_safe(getattr(entity, name))
        for name in fields
        if not is_sensitive(name)
    }


def diff(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> dict[str, dict[str, Any]] | None:
    """`{campo: {before, after}}` solo con los campos que cambiaron.

    `before=None` (creacion) o `after=None` (borrado de una asignacion) dan
    todos los campos del otro lado. Campos sensibles se descartan siempre.
    Devuelve `None` si no hay cambios.
    """
    before, after = before or {}, after or {}
    changes = {}
    for name in sorted(set(before) | set(after)):
        if is_sensitive(name):
            continue
        old, new = json_safe(before.get(name)), json_safe(after.get(name))
        if old != new:
            changes[name] = {"before": old, "after": new}
    return changes or None


@dataclass
class AuditEntry:
    """Evento a registrar. `application_id` = app duena del tag; si es
    `None`, el escritor usa la app `leo`."""

    action_tag: str
    result: str = "ok"
    actor_user_id: UUID | None = None
    actor_username: str | None = None
    application_id: UUID | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    changes: dict[str, Any] | None = None
    reason: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    session_id: UUID | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class Actor:
    """Quien hace una mutacion (usuario de la sesion + datos de la peticion);
    arma los `AuditEntry` de los controllers sin repetir esos campos."""

    user_id: UUID | None
    username: str | None
    session_id: UUID | None
    meta: RequestMeta

    def entry(self, action_tag: str, **fields: Any) -> AuditEntry:
        return AuditEntry(
            action_tag=action_tag,
            actor_user_id=self.user_id,
            actor_username=self.username,
            session_id=self.session_id,
            ip=self.meta.ip,
            user_agent=self.meta.user_agent,
            request_id=self.meta.request_id,
            **fields,
        )
