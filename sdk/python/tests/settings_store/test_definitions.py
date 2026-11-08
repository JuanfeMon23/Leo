"""Definiciones y registro: validacion pura, sin BD."""

import pytest

from leo_sdk.settings_store import (
    SettingDef,
    SettingOutOfRangeError,
    SettingsRegistry,
    SettingTypeMismatchError,
    UnknownSettingError,
)


def make(**over):
    base = {
        "key": "auth.max_attempts",
        "type": "int",
        "default": 5,
        "description": "Intentos.",
        "min": 3,
        "max": 20,
    }
    return SettingDef(**{**base, **over})


@pytest.mark.parametrize(
    "key",
    ["x", "Auth.x", "auth.", ".x", "auth..x", "auth.x-y", "auth.x y", "a." + "b" * 100],
)
def test_invalid_keys_rejected(key):
    with pytest.raises(ValueError):
        make(key=key)


@pytest.mark.parametrize("key", ["auth.x", "a1_b.c_2.d", "rate_limit.window_seconds"])
def test_valid_keys(key):
    assert make(key=key).key == key


def test_group_defaults_to_first_segment():
    assert make().group == "auth"
    assert make(group="seguridad").group == "seguridad"


@pytest.mark.parametrize(
    "over",
    [
        {"type": "decimal"},
        {"default": 2},  # fuera de rango
        {"default": True},  # bool no es int
        {"default": "5"},
        {"min": 10, "max": 3, "default": 5},
        {"min": 1.5},  # int con limite float
        {"type": "bool", "default": True, "min": 1},
        {"description": "  "},
        {"unit": ""},
        {"group": "g" * 41},
    ],
)
def test_invalid_definitions_rejected(over):
    with pytest.raises(ValueError):
        make(**over)


def test_float_default_normalized_and_bounds_inclusive():
    definition = make(key="ui.ratio", type="float", default=1, min=0.5, max=3)
    assert definition.default == 1.0 and isinstance(definition.default, float)
    assert definition.coerce(3) == 3.0 and definition.coerce(0.5) == 0.5


def test_coerce_types():
    definition = make()
    assert definition.coerce(10) == 10
    for bad in ("10", 10.5, True, None, [1]):
        with pytest.raises(SettingTypeMismatchError):
            definition.coerce(bad)
    for bad in (2, 21):
        with pytest.raises(SettingOutOfRangeError) as exc:
            definition.coerce(bad)
        assert exc.value.details["min"] == 3 and exc.value.details["max"] == 20
    boolean = make(key="a.b", type="bool", default=False, min=None, max=None)
    assert boolean.coerce(True) is True
    with pytest.raises(SettingTypeMismatchError):
        boolean.coerce(1)
    with pytest.raises(SettingTypeMismatchError):
        make(key="a.f", type="float", default=1.0, min=None, max=None).coerce(
            float("nan")
        )


def test_registry_unique_and_lookup():
    reg = SettingsRegistry([make()])
    with pytest.raises(ValueError):
        reg.register(make())
    assert reg.get("auth.max_attempts").default == 5
    assert "auth.max_attempts" in reg and len(reg) == 1
    with pytest.raises(UnknownSettingError):
        reg.get("nope.x")
