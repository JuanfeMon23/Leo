"""`SettingsStore`: lectura tipada con cache, escritura con historial.

Lectura (`get`/`get_many`): cache en proceso con TTL corto, invalidada al
instante al escribir en ESTE proceso (otros procesos ven el cambio como
maximo tras el TTL). Nunca lanza por fallos de BD ni devuelve un valor fuera
de rango: si la fila falta, esta corrupta o la BD falla, devuelve el default
del registro y registra el fallo.

Escritura (`update`): valida tipo y rango, bloqueo optimista por `version` y
escribe `settings` + `settings_history` en la misma transaccion.
"""

import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from leo_sdk.settings_store.definitions import SettingDef, SettingsRegistry
from leo_sdk.settings_store.errors import (
    ReasonRequiredError,
    SettingInvalidValueError,
    SettingNotFoundError,
    SettingsError,
    SettingsUnavailableError,
    VersionConflictError,
)
from leo_sdk.settings_store.schema import SettingsModels

logger = logging.getLogger("leo_sdk.settings_store")

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

REASON_MIN_LENGTH = 3
REASON_MAX_LENGTH = 500
MAX_CACHE_TTL_SECONDS = 15.0
# Tras un fallo de BD, el default se cachea poco para no martillar la BD caida.
FALLBACK_TTL_SECONDS = 2.0
SYSTEM_USERNAME = "system"


@dataclass(frozen=True)
class SettingsActor:
    """Quien cambia un ajuste (el sistema: `user_id=None`)."""

    user_id: UUID | None = None
    username: str | None = None
    request_id: str | None = None


SYSTEM_ACTOR = SettingsActor(None, SYSTEM_USERNAME)


@dataclass(frozen=True)
class SettingView:
    key: str
    type: str
    value: Any
    default: Any
    min: int | float | None
    max: int | float | None
    unit: str | None
    group: str
    description: str
    requires_security_permission: bool
    version: int
    updated_at: datetime | None
    updated_by: UUID | None
    updated_by_username: str | None


@dataclass(frozen=True)
class SettingChange:
    key: str
    before: Any
    after: Any
    reason: str
    view: SettingView


@dataclass(frozen=True)
class HistoryEntry:
    id: UUID
    setting_key: str
    old_value: Any
    new_value: Any
    version_after: int
    changed_by: UUID | None
    changed_by_username: str | None
    changed_at: datetime
    reason: str
    request_id: str | None


@dataclass(frozen=True)
class HistoryPage:
    items: list[HistoryEntry]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class SyncResult:
    inserted: list[str]
    updated: list[str]
    adjusted: list[str]


def _validated_reason(reason: str | None) -> str:
    text = (reason or "").strip()
    if not REASON_MIN_LENGTH <= len(text) <= REASON_MAX_LENGTH:
        raise ReasonRequiredError(REASON_MIN_LENGTH, REASON_MAX_LENGTH)
    return text


def _db_attr(exc: DBAPIError, attr: str) -> str | None:
    orig = exc.orig
    return getattr(orig, attr, None) or getattr(
        getattr(orig, "__cause__", None), attr, None
    )


class SettingsStore:
    def __init__(
        self,
        registry: SettingsRegistry,
        session_factory: SessionFactory,
        models: SettingsModels,
        *,
        cache_ttl: float = 10.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 <= cache_ttl <= MAX_CACHE_TTL_SECONDS:
            raise ValueError(
                f"cache_ttl debe estar entre 0 y {MAX_CACHE_TTL_SECONDS:g} segundos."
            )
        self.registry = registry
        # Reemplazable (p. ej. los tests de la app lo atan a su sesion).
        self.session_factory = session_factory
        self.models = models
        self.cache_ttl = cache_ttl
        self._monotonic = monotonic
        self._cache: dict[str, tuple[Any, float]] = {}

    # --- cache ---

    def invalidate(self, key: str | None = None) -> None:
        """Descarta la cache (de una clave o toda). Llamarlo tras escribir
        las tablas por fuera del store."""
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)

    def _cached(self, key: str) -> tuple[bool, Any]:
        hit = self._cache.get(key)
        if hit is None:
            return False, None
        value, expires = hit
        if self._monotonic() >= expires:
            del self._cache[key]
            return False, None
        return True, value

    def _remember(self, key: str, value: Any, ttl: float) -> None:
        if ttl > 0:
            self._cache[key] = (value, self._monotonic() + ttl)

    # --- lectura ---

    def _usable(self, definition: SettingDef, stored: Any) -> bool:
        return definition.is_valid(stored)

    async def get(self, key: str) -> Any:
        """Valor vigente (tipado). `UnknownSettingError` solo si la clave no
        esta en el registro; nunca por la BD."""
        return (await self.get_many([key]))[key]

    async def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        wanted = list(dict.fromkeys(keys))
        defs = {key: self.registry.get(key) for key in wanted}
        result: dict[str, Any] = {}
        missing: list[str] = []
        for key in wanted:
            hit, value = self._cached(key)
            if hit:
                result[key] = value
            else:
                missing.append(key)
        if not missing:
            return result
        try:
            async with self.session_factory() as session:
                rows = (
                    await session.execute(
                        select(
                            self.models.Setting.key, self.models.Setting.value
                        ).where(self.models.Setting.key.in_(missing))
                    )
                ).all()
        except Exception:
            logger.exception(
                "No se pudieron leer los ajustes %s; se usan los valores por defecto.",
                missing,
            )
            for key in missing:
                result[key] = defs[key].default
                self._remember(key, defs[key].default, self._fallback_ttl())
            return result
        stored = {row[0]: row[1] for row in rows}
        for key in missing:
            definition = defs[key]
            if key not in stored:
                logger.warning(
                    "El ajuste %s no existe en la BD; se usa el valor por defecto.",
                    key,
                )
                result[key] = definition.default
                self._remember(key, definition.default, self._fallback_ttl())
            elif not self._usable(definition, stored[key]):
                logger.error(
                    "El ajuste %s tiene un valor inválido en la BD (%r); se usa "
                    "el valor por defecto.",
                    key,
                    stored[key],
                )
                result[key] = definition.default
                self._remember(key, definition.default, self._fallback_ttl())
            else:
                result[key] = definition.coerce(stored[key])
                self._remember(key, result[key], self.cache_ttl)
        return result

    def _fallback_ttl(self) -> float:
        return min(self.cache_ttl, FALLBACK_TTL_SECONDS)

    def _view(self, definition: SettingDef, row: Any | None) -> SettingView:
        value = definition.default
        if row is not None and self._usable(definition, row.value):
            value = definition.coerce(row.value)
        return SettingView(
            key=definition.key,
            type=definition.type,
            value=value,
            default=definition.default,
            min=definition.min,
            max=definition.max,
            unit=definition.unit,
            group=definition.group,
            description=definition.description,
            requires_security_permission=definition.requires_security,
            version=row.version if row is not None else 0,
            updated_at=row.updated_at if row is not None else None,
            updated_by=row.updated_by if row is not None else None,
            updated_by_username=row.updated_by_username if row is not None else None,
        )

    async def list(self) -> dict[str, list[SettingView]]:
        """Todos los ajustes del registro, agrupados por `group` (grupos y
        claves en orden alfabetico). Lanza `SettingsUnavailableError` si la
        BD falla (a diferencia de `get`)."""
        model = self.models.Setting
        try:
            async with self.session_factory() as session:
                rows = (await session.execute(select(model))).scalars().all()
        except SQLAlchemyError as exc:
            logger.exception("No se pudo listar los ajustes.")
            raise SettingsUnavailableError from exc
        by_key = {row.key: row for row in rows}
        grouped: dict[str, list[SettingView]] = {}
        for definition in sorted(self.registry, key=lambda d: (d.group, d.key)):
            grouped.setdefault(definition.group, []).append(
                self._view(definition, by_key.get(definition.key))
            )
        return grouped

    async def history(
        self, key: str, page: int = 1, page_size: int = 20
    ) -> HistoryPage:
        """Cambios de una clave, del mas reciente al mas antiguo."""
        page, page_size = max(1, page), min(max(1, page_size), 100)
        model = self.models.SettingHistory
        try:
            async with self.session_factory() as session:
                total = (
                    await session.execute(
                        select(func.count())
                        .select_from(model)
                        .where(model.setting_key == key)
                    )
                ).scalar_one()
                rows = (
                    (
                        await session.execute(
                            select(model)
                            .where(model.setting_key == key)
                            .order_by(model.changed_at.desc(), model.id.desc())
                            .limit(page_size)
                            .offset((page - 1) * page_size)
                        )
                    )
                    .scalars()
                    .all()
                )
        except SQLAlchemyError as exc:
            logger.exception("No se pudo leer el historial de %s.", key)
            raise SettingsUnavailableError from exc
        items = [
            HistoryEntry(
                id=r.id,
                setting_key=r.setting_key,
                old_value=r.old_value,
                new_value=r.new_value,
                version_after=r.version_after,
                changed_by=r.changed_by,
                changed_by_username=r.changed_by_username,
                changed_at=r.changed_at,
                reason=r.reason,
                request_id=r.request_id,
            )
            for r in rows
        ]
        return HistoryPage(items=items, page=page, page_size=page_size, total=total)

    # --- escritura ---

    async def update(
        self,
        key: str,
        value: Any,
        reason: str,
        actor: SettingsActor,
        expected_version: int,
        *,
        session: AsyncSession | None = None,
    ) -> SettingChange:
        """Cambia el valor de `key`. Con `session` propia no hace commit (lo
        hace quien llama); sin ella abre una y confirma.

        Errores (`SettingsError`): `setting_not_found`, `setting_type_mismatch`,
        `setting_out_of_range`, `reason_required`, `version_conflict`,
        `setting_invalid_value`."""
        if key not in self.registry:
            raise SettingNotFoundError(key)
        definition = self.registry.get(key)
        reason = _validated_reason(reason)
        new_value = definition.coerce(value)
        owns = session is None
        context: AbstractAsyncContextManager[AsyncSession] = (
            self.session_factory() if owns else nullcontext(session)  # type: ignore[arg-type]
        )
        try:
            async with context as active:
                change = await self._write(
                    active, definition, new_value, reason, actor, expected_version
                )
                if owns:
                    await active.commit()
        except DBAPIError as exc:
            self.invalidate(key)
            raise self._domain_error(exc) from exc
        self.invalidate(key)
        return change

    async def _write(
        self,
        session: AsyncSession,
        definition: SettingDef,
        new_value: Any,
        reason: str,
        actor: SettingsActor,
        expected_version: int,
    ) -> SettingChange:
        model, history = self.models.Setting, self.models.SettingHistory
        row = (
            await session.execute(
                select(model).where(model.key == definition.key).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise SettingNotFoundError(definition.key)
        if row.version != expected_version:
            raise VersionConflictError(definition.key, expected_version, row.version)
        old_value = row.value
        row.value = new_value
        row.version = row.version + 1
        row.updated_by = actor.user_id
        row.updated_by_username = actor.username
        session.add(
            history(
                setting_key=definition.key,
                old_value=old_value,
                new_value=new_value,
                version_after=row.version,
                changed_by=actor.user_id,
                changed_by_username=actor.username,
                reason=reason,
                request_id=actor.request_id,
            )
        )
        await session.flush()
        await session.refresh(row)
        return SettingChange(
            key=definition.key,
            before=old_value,
            after=new_value,
            reason=reason,
            view=self._view(definition, row),
        )

    @staticmethod
    def _domain_error(exc: DBAPIError) -> SettingsError:
        sqlstate = _db_attr(exc, "sqlstate")
        if sqlstate == "23514":
            return SettingInvalidValueError(
                "El valor no cumple las reglas permitidas para este ajuste."
            )
        if sqlstate == "22001":
            return SettingInvalidValueError(
                "Uno de los textos es demasiado largo (el motivo admite hasta "
                f"{REASON_MAX_LENGTH} caracteres)."
            )
        logger.exception("Error de BD al guardar un ajuste (SQLSTATE %s).", sqlstate)
        return SettingsUnavailableError()

    # --- arranque ---

    async def sync_registry(
        self, initial_values: Mapping[str, Any] | None = None
    ) -> SyncResult:
        """Alinea la BD con el registro de codigo (llamar al arrancar).

        - Clave faltante: se INSERTA con `initial_values[key]` (si es valido;
          p. ej. un valor heredado de una variable de entorno) o el default.
        - Clave existente: se ACTUALIZAN solo los metadatos (min/max/default/
          descripcion/grupo/unidad/requires_security/tipo) sin tocar `value`.
          Si el valor vigente queda fuera del nuevo rango (o cambio el tipo),
          se ajusta al limite (al default si cambio el tipo) y se registra en
          `settings_history` con motivo de sistema.
        - Claves de la BD que ya no estan en el registro: no se tocan.
        """
        initial = dict(initial_values or {})
        model, history = self.models.Setting, self.models.SettingHistory
        inserted: list[str] = []
        updated: list[str] = []
        adjusted: list[str] = []
        async with self.session_factory() as session:
            to_insert = []
            for definition in self.registry:
                start = definition.default
                if definition.key in initial:
                    if definition.is_valid(initial[definition.key]):
                        start = definition.coerce(initial[definition.key])
                    else:
                        logger.warning(
                            "Valor inicial inválido para %s (%r); se usa el default.",
                            definition.key,
                            initial[definition.key],
                        )
                to_insert.append(self._row_values(definition, start))
            if to_insert:
                result = await session.execute(
                    pg_insert(model)
                    .values(to_insert)
                    .on_conflict_do_nothing(index_elements=["key"])
                    .returning(model.key)
                )
                inserted = [r[0] for r in result.all()]
            keys = self.registry.keys()
            rows = (
                (
                    await session.execute(
                        select(model).where(model.key.in_(keys)).with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                if row.key in inserted:
                    continue
                definition = self.registry.get(row.key)
                changed = self._sync_metadata(row, definition)
                fix = self._range_fix(row, definition)
                if fix is not None:
                    new_value, why = fix
                    session.add(
                        history(
                            setting_key=row.key,
                            old_value=row.value,
                            new_value=new_value,
                            version_after=row.version + 1,
                            changed_by=None,
                            changed_by_username=SYSTEM_USERNAME,
                            reason=why,
                        )
                    )
                    row.value = new_value
                    row.version += 1
                    row.updated_by = None
                    row.updated_by_username = SYSTEM_USERNAME
                    adjusted.append(row.key)
                    changed = True
                if changed:
                    updated.append(row.key)
            await session.commit()
        self.invalidate()
        return SyncResult(inserted=inserted, updated=updated, adjusted=adjusted)

    @staticmethod
    def _row_values(definition: SettingDef, value: Any) -> dict[str, Any]:
        return {
            "key": definition.key,
            "value": value,
            "value_type": definition.type,
            "min_value": definition.min,
            "max_value": definition.max,
            "default_value": definition.default,
            "unit": definition.unit,
            "group_name": definition.group,
            "description": definition.description,
            "requires_security_permission": definition.requires_security,
        }

    @staticmethod
    def _sync_metadata(row: Any, definition: SettingDef) -> bool:
        wanted = {
            "value_type": definition.type,
            "min_value": definition.min,
            "max_value": definition.max,
            "default_value": definition.default,
            "unit": definition.unit,
            "group_name": definition.group,
            "description": definition.description,
            "requires_security_permission": definition.requires_security,
        }
        changed = False
        for column, new in wanted.items():
            if getattr(row, column) != new:
                setattr(row, column, new)
                changed = True
        return changed

    @staticmethod
    def _range_fix(row: Any, definition: SettingDef) -> tuple[Any, str] | None:
        """(nuevo valor, motivo) si el valor vigente ya no es valido."""
        current = row.value
        if definition.is_valid(current):
            normalized = definition.coerce(current)
            return None if normalized == current else (normalized, _TYPE_REASON)
        numeric = definition.type in ("int", "float")
        is_number = isinstance(current, int | float) and not isinstance(current, bool)
        if (
            numeric
            and is_number
            and (definition.type == "float" or isinstance(current, int))
        ):
            clamped = definition.coerce(definition.clamp(current))
            limit = "mínimo" if clamped == definition.min else "máximo"
            return clamped, (
                "Ajuste automático del sistema: el valor quedó fuera del nuevo "
                f"rango permitido y se llevó al {limit} ({clamped})."
            )
        return definition.default, _TYPE_REASON


_TYPE_REASON = (
    "Ajuste automático del sistema: el tipo del ajuste cambió y el valor se "
    "restableció al valor por defecto."
)

__all__ = [
    "SYSTEM_ACTOR",
    "HistoryEntry",
    "HistoryPage",
    "SessionFactory",
    "SettingChange",
    "SettingView",
    "SettingsActor",
    "SettingsStore",
    "SyncResult",
]

# Para anotar callbacks de auditoria en las apps.
AuditCallback = Callable[[Any, str, Any, Any, str], Awaitable[None]]
