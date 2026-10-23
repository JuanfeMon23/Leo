"""SettingsStore contra PostgreSQL real (transaccion revertida por test)."""

import logging

import pytest
from sqlalchemy import select, text

from leo_sdk.settings_store import (
    SettingDef,
    SettingInvalidValueError,
    SettingNotFoundError,
    SettingOutOfRangeError,
    SettingsActor,
    SettingsRegistry,
    SettingsStore,
    SettingTypeMismatchError,
    UnknownSettingError,
    VersionConflictError,
)
from leo_sdk.settings_store.errors import ReasonRequiredError

from .conftest import MODELS, REGISTRY_DEFS

Setting, History = MODELS.Setting, MODELS.SettingHistory
ACTOR = SettingsActor(None, "ana", "req-1")


async def row(session, key):
    return (
        await session.execute(select(Setting).where(Setting.key == key))
    ).scalar_one()


async def history_rows(session, key):
    return (
        (await session.execute(select(History).where(History.setting_key == key)))
        .scalars()
        .all()
    )


async def test_sync_inserts_defaults_and_initial_values(
    registry, shared_factory, clock, session
):
    store = SettingsStore(registry, shared_factory, MODELS, monotonic=clock)
    result = await store.sync_registry({"auth.idle_minutes": 45, "ui.ratio": 99})
    assert sorted(result.inserted) == sorted(d.key for d in REGISTRY_DEFS)
    assert (await row(session, "auth.idle_minutes")).value == 45
    # Valor inicial fuera de rango: se ignora y queda el default.
    assert (await row(session, "ui.ratio")).value == 1.5
    r = await row(session, "auth.max_attempts")
    assert (r.value, r.version, r.min_value, r.max_value, r.unit) == (
        5,
        1,
        3,
        20,
        "count",
    )
    assert r.requires_security_permission is True and r.group_name == "auth"


async def test_sync_is_idempotent_and_keeps_values(store, session):
    await store.update("auth.idle_minutes", 60, "porque sí", ACTOR, 1)
    again = await store.sync_registry({"auth.idle_minutes": 10})
    assert again.inserted == [] and again.updated == [] and again.adjusted == []
    r = await row(session, "auth.idle_minutes")
    assert (r.value, r.version) == (60, 2)  # el initial_value no pisa el vigente


async def test_sync_updates_metadata_without_touching_value(
    store, session, shared_factory
):
    await store.update("auth.idle_minutes", 60, "ajuste", ACTOR, 1)
    new = SettingsRegistry(
        [
            SettingDef(
                "auth.idle_minutes",
                "int",
                20,
                "Nueva descripción.",
                min=10,
                max=240,
                unit="minutes",
                group="seguridad",
                requires_security=True,
            )
        ]
    )
    other = SettingsStore(new, shared_factory, MODELS)
    result = await other.sync_registry()
    assert result.updated == ["auth.idle_minutes"] and result.adjusted == []
    r = await row(session, "auth.idle_minutes")
    assert r.value == 60 and r.version == 2
    assert (r.min_value, r.max_value, r.default_value) == (10, 240, 20)
    assert (r.description, r.group_name, r.requires_security_permission) == (
        "Nueva descripción.",
        "seguridad",
        True,
    )


@pytest.mark.parametrize(
    ("stored", "new_min", "new_max", "expected"),
    [(30, 40, 100, 40), (30, 5, 20, 20)],
)
async def test_sync_clamps_value_outside_new_range_and_logs_history(
    store, session, shared_factory, stored, new_min, new_max, expected
):
    await store.update("auth.idle_minutes", stored, "base", ACTOR, 1)
    other = SettingsStore(
        SettingsRegistry(
            [
                SettingDef(
                    "auth.idle_minutes",
                    "int",
                    new_min,
                    "Inactividad.",
                    min=new_min,
                    max=new_max,
                    group="auth",
                )
            ]
        ),
        shared_factory,
        MODELS,
    )
    result = await other.sync_registry()
    assert result.adjusted == ["auth.idle_minutes"]
    r = await row(session, "auth.idle_minutes")
    assert r.value == expected and r.version == 3
    last = max(
        await history_rows(session, "auth.idle_minutes"), key=lambda h: h.version_after
    )
    assert (last.old_value, last.new_value, last.version_after) == (stored, expected, 3)
    assert last.changed_by is None and last.changed_by_username == "system"
    assert "Ajuste automático del sistema" in last.reason


async def test_get_typed_values(store):
    assert await store.get("auth.max_attempts") == 5
    assert await store.get("ui.ratio") == 1.5
    assert await store.get("ui.compact") is False
    assert await store.get("ui.title") == "Hola"
    assert await store.get_many(["ui.title", "auth.idle_minutes"]) == {
        "ui.title": "Hola",
        "auth.idle_minutes": 30,
    }
    with pytest.raises(UnknownSettingError):
        await store.get("no.existe")


async def test_update_writes_setting_and_history(store, session, user_id):
    actor = SettingsActor(user_id, "ana", "req-9")
    change = await store.update("auth.idle_minutes", 45, "  Política nueva ", actor, 1)
    assert (change.before, change.after, change.reason) == (30, 45, "Política nueva")
    assert change.view.version == 2 and change.view.value == 45
    r = await row(session, "auth.idle_minutes")
    assert (r.value, r.version, r.updated_by, r.updated_by_username) == (
        45,
        2,
        user_id,
        "ana",
    )
    [h] = await history_rows(session, "auth.idle_minutes")
    assert (h.old_value, h.new_value, h.version_after, h.reason) == (
        30,
        45,
        2,
        "Política nueva",
    )
    assert (h.changed_by, h.changed_by_username, h.request_id) == (
        user_id,
        "ana",
        "req-9",
    )
    assert await store.get("auth.idle_minutes") == 45


async def test_update_float_accepts_int_and_stores_float(store):
    change = await store.update("ui.ratio", 2, "razón", ACTOR, 1)
    assert change.after == 2.0 and isinstance(change.after, float)


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        ("auth.idle_minutes", "45", SettingTypeMismatchError),
        ("auth.idle_minutes", 45.5, SettingTypeMismatchError),
        ("auth.idle_minutes", True, SettingTypeMismatchError),
        ("ui.compact", 1, SettingTypeMismatchError),
        ("ui.title", 5, SettingTypeMismatchError),
        ("auth.idle_minutes", 4, SettingOutOfRangeError),
        ("auth.idle_minutes", 121, SettingOutOfRangeError),
        ("ui.ratio", 3.1, SettingOutOfRangeError),
    ],
)
async def test_update_rejects_invalid_values(store, session, key, value, error):
    with pytest.raises(error):
        await store.update(key, value, "motivo", ACTOR, 1)
    assert await history_rows(session, key) == []
    assert (await row(session, key)).version == 1


async def test_out_of_range_error_carries_limits_in_spanish(store):
    with pytest.raises(SettingOutOfRangeError) as exc:
        await store.update("auth.idle_minutes", 500, "motivo", ACTOR, 1)
    assert exc.value.details == {
        "key": "auth.idle_minutes",
        "value": 500,
        "min": 5,
        "max": 120,
    }
    assert "entre 5 y 120 minutes" in exc.value.message


@pytest.mark.parametrize("reason", [None, "", "  ", "ab", "x" * 501])
async def test_update_requires_reason(store, reason):
    with pytest.raises(ReasonRequiredError):
        await store.update("auth.idle_minutes", 45, reason, ACTOR, 1)


async def test_optimistic_locking(store, session):
    await store.update("auth.idle_minutes", 45, "primero", ACTOR, 1)
    with pytest.raises(VersionConflictError) as exc:
        await store.update("auth.idle_minutes", 50, "segundo", ACTOR, 1)
    assert exc.value.status_code == 409
    assert exc.value.details["current_version"] == 2
    assert (await row(session, "auth.idle_minutes")).value == 45
    assert len(await history_rows(session, "auth.idle_minutes")) == 1
    await store.update("auth.idle_minutes", 50, "segundo", ACTOR, 2)


async def test_update_unknown_or_unsynced_key(store, session, registry):
    with pytest.raises(SettingNotFoundError):
        await store.update("no.existe", 1, "motivo", ACTOR, 1)
    registry.register(SettingDef("extra.one", "int", 1, "Nueva sin sync."))
    with pytest.raises(SettingNotFoundError):
        await store.update("extra.one", 2, "motivo", ACTOR, 1)


async def test_db_check_violation_becomes_domain_error(store, session, registry):
    # El registro permite 200 pero la fila (sin sincronizar) solo hasta 120.
    wide = SettingsRegistry(
        [SettingDef("auth.idle_minutes", "int", 30, "x", min=5, max=500, group="auth")]
    )
    loose = SettingsStore(wide, store.session_factory, MODELS)
    with pytest.raises(SettingInvalidValueError) as exc:
        await loose.update("auth.idle_minutes", 300, "motivo", ACTOR, 1)
    assert exc.value.code == "setting_invalid_value"


async def test_history_is_append_only(store, session):
    await store.update("auth.idle_minutes", 45, "primero", ACTOR, 1)
    for sql in (
        "UPDATE settings_history SET reason = 'otro motivo'",
        "DELETE FROM settings_history",
        "TRUNCATE settings_history",
    ):
        with pytest.raises(Exception, match="append-only"):
            async with session.begin_nested():
                await session.execute(text(sql))


async def test_history_pages_newest_first(store):
    for version, value in enumerate([10, 11, 12], start=1):
        await store.update(
            "auth.idle_minutes", value, f"cambio {value}", ACTOR, version
        )
    page1 = await store.history("auth.idle_minutes", page=1, page_size=2)
    assert page1.total == 3 and [h.new_value for h in page1.items] == [12, 11]
    page2 = await store.history("auth.idle_minutes", page=2, page_size=2)
    assert [h.new_value for h in page2.items] == [10]
    assert (await store.history("ui.title")).total == 0


async def test_list_groups_alphabetically(store):
    grouped = await store.list()
    assert list(grouped) == ["auth", "ui"]
    assert [v.key for v in grouped["auth"]] == [
        "auth.idle_minutes",
        "auth.max_attempts",
    ]
    view = grouped["auth"][1]
    assert (view.value, view.default, view.min, view.max, view.unit, view.version) == (
        5,
        5,
        3,
        20,
        "count",
        1,
    )
    assert view.requires_security_permission is True and view.updated_at is not None


async def test_cache_ttl_and_local_invalidation(store, session, clock):
    assert await store.get("auth.idle_minutes") == 30
    # Cambio por fuera del store: la cache lo oculta hasta que vence el TTL.
    await session.execute(
        text("UPDATE settings SET value = '77'::jsonb WHERE key = 'auth.idle_minutes'")
    )
    assert await store.get("auth.idle_minutes") == 30
    clock.now += 9
    assert await store.get("auth.idle_minutes") == 30
    clock.now += 2
    assert await store.get("auth.idle_minutes") == 77
    # Escribir con el store invalida al instante (sin esperar el TTL).
    await store.update("auth.idle_minutes", 50, "motivo", ACTOR, 1)
    assert await store.get("auth.idle_minutes") == 50
    await session.execute(
        text("UPDATE settings SET value = '60'::jsonb WHERE key = 'auth.idle_minutes'")
    )
    store.invalidate("auth.idle_minutes")
    assert await store.get("auth.idle_minutes") == 60


def test_cache_ttl_must_be_short(registry, shared_factory):
    with pytest.raises(ValueError):
        SettingsStore(registry, shared_factory, MODELS, cache_ttl=60)


async def test_get_falls_back_to_default_when_db_fails(registry, clock, caplog):
    def broken():
        raise ConnectionError("BD caída")

    store = SettingsStore(registry, broken, MODELS, monotonic=clock)
    with caplog.at_level(logging.ERROR, logger="leo_sdk.settings_store"):
        assert await store.get("auth.idle_minutes") == 30
        assert await store.get_many(["ui.title", "ui.compact"]) == {
            "ui.title": "Hola",
            "ui.compact": False,
        }
    assert "No se pudieron leer los ajustes" in caplog.text


async def test_get_falls_back_when_row_missing_or_value_out_of_range(
    registry, shared_factory, clock, session, caplog
):
    store = SettingsStore(registry, shared_factory, MODELS, monotonic=clock)
    assert await store.get("auth.idle_minutes") == 30  # sin fila (no hubo sync)
    await store.sync_registry()
    # Fila corrompida por fuera de la API (la BD admite el rango viejo).
    await session.execute(
        text(
            "UPDATE settings SET min_value = NULL, max_value = NULL WHERE key = 'auth.idle_minutes'"
        )
    )
    await session.execute(
        text(
            "UPDATE settings SET value = '9999'::jsonb WHERE key = 'auth.idle_minutes'"
        )
    )
    store.invalidate()
    with caplog.at_level(logging.ERROR, logger="leo_sdk.settings_store"):
        assert await store.get("auth.idle_minutes") == 30
    assert "valor inválido" in caplog.text


async def test_failed_fallback_is_cached_briefly(registry, clock):
    calls = []

    def broken():
        calls.append(1)
        raise ConnectionError("BD caída")

    store = SettingsStore(registry, broken, MODELS, monotonic=clock)
    await store.get("ui.title")
    await store.get("ui.title")
    assert len(calls) == 1
    clock.now += 3
    await store.get("ui.title")
    assert len(calls) == 2
