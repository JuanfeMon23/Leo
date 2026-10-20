"""Auditoria desde la app: `diff` seguro y cliente de ingesta en Leo.

Fallo de red: el evento va a una cola acotada en memoria (con `actor_user_id`
en vez del token del usuario) y se reintenta en el siguiente `record()` o con
`flush()`. Es simple a proposito: la cola se pierde si el proceso muere y no se
comparte entre instancias (pendiente documentado). Un fallo NUNCA propaga
excepcion a la peticion de negocio.
"""

import logging
from collections import deque
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from leo_sdk.client import LeoClient
from leo_sdk.errors import LeoError, LeoUnavailableError
from leo_sdk.models import LeoUser
from leo_sdk.tags import validate_tag

logger = logging.getLogger("leo_sdk.audit")

DEFAULT_SENSITIVE: tuple[str, ...] = ("password", "secret", "token", "hash")


def _is_sensitive(key: object, sensitive: Iterable[str]) -> bool:
    name = str(key).lower()
    return any(part.lower() in name for part in sensitive)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID | Decimal):
        return str(value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def scrub(value: Any, sensitive: Iterable[str] = DEFAULT_SENSITIVE) -> Any:
    """Copia JSON-segura de `value` sin claves sensibles (recursivo)."""
    sensitive = tuple(sensitive)
    if isinstance(value, Mapping):
        return {
            str(k): scrub(v, sensitive)
            for k, v in value.items()
            if not _is_sensitive(k, sensitive)
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [scrub(v, sensitive) for v in value]
    return _jsonable(value)


def diff(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    sensitive: Iterable[str] = DEFAULT_SENSITIVE,
) -> dict[str, dict[str, Any]]:
    """`{campo: {before, after}}` solo de los campos que cambiaron. Los campos
    sensibles (nombre que contenga password/secret/token/hash, configurable) no
    aparecen nunca, ni anidados."""
    sensitive = tuple(sensitive)
    before, after = before or {}, after or {}
    changes: dict[str, dict[str, Any]] = {}
    for key in {**before, **after}:
        if _is_sensitive(key, sensitive):
            continue
        old = scrub(before.get(key), sensitive)
        new = scrub(after.get(key), sensitive)
        if old != new:
            changes[str(key)] = {"before": old, "after": new}
    return changes


class AuditClient:
    def __init__(
        self,
        client: LeoClient,
        *,
        sensitive: Iterable[str] = DEFAULT_SENSITIVE,
        queue_size: int | None = None,
    ) -> None:
        self._client = client
        self._sensitive = tuple(sensitive)
        size = queue_size or client.settings.audit_queue_size
        self._queue: deque[dict[str, Any]] = deque(maxlen=size)

    @property
    def pending(self) -> int:
        return len(self._queue)

    def diff(
        self, before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
    ) -> dict[str, dict[str, Any]]:
        return diff(before, after, sensitive=self._sensitive)

    async def record(
        self,
        action_tag: str,
        result: str = "ok",
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        changes: Mapping[str, Any] | None = None,
        reason: str | None = None,
        actor: LeoUser | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> bool:
        """Envia el evento a Leo. True si quedo registrado; False si se encolo
        o se descarto (se loguea). No lanza por fallos de red ni de Leo; solo
        por un `action_tag` mal formado (error de codigo)."""
        validate_tag(action_tag)
        payload: dict[str, Any] = {
            "action_tag": action_tag,
            "result": result,
            "entity_type": entity_type,
            "entity_id": None if entity_id is None else str(entity_id),
            "changes": None if changes is None else scrub(changes, self._sensitive),
            "reason": reason,
            "ip": ip,
            "user_agent": user_agent,
            "request_id": request_id,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        await self.flush()
        fallback = dict(payload)
        if actor is not None and actor.is_service:
            # Leo aun no admite un actor de servicio en la ingesta: se omite el
            # actor y la app llamadora queda en `reason`.
            note = f"[servicio: {actor.client_id}]"
            payload["reason"] = f"{note} {reason}" if reason else note
            fallback = dict(payload)
        elif actor is not None:
            payload["actor"] = {"access_token": actor.access_token, "jkt": actor.jkt}
            fallback["actor_user_id"] = str(actor.id)
        return await self._send(payload, fallback)

    async def flush(self) -> int:
        """Reintenta la cola en orden; devuelve cuantos se enviaron."""
        sent = 0
        while self._queue:
            try:
                await self._client.ingest_audit(self._queue[0])
            except LeoUnavailableError:
                break
            except LeoError as exc:
                self._log_rejected(exc)  # no se reintenta: Leo lo rechazo
            self._queue.popleft()
            sent += 1
        return sent

    async def _send(self, payload: dict[str, Any], fallback: dict[str, Any]) -> bool:
        try:
            await self._client.ingest_audit(payload)
            return True
        except LeoUnavailableError:
            self._queue.append(fallback)
            logger.warning("Leo no disponible: evento de auditoría encolado.")
            return False
        except LeoError as exc:
            if exc.code == "invalid_actor" and "actor" in payload:
                return await self._send(fallback, fallback)  # por actor_user_id
            self._log_rejected(exc)
            return False

    @staticmethod
    def _log_rejected(exc: LeoError) -> None:
        logger.error(
            "Leo rechazó un evento de auditoría (%s): %s", exc.code, exc.message
        )
