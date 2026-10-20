"""El ejemplo del README se importa y su catalogo cubre sus require_action."""

import importlib

import pytest


def test_minimal_app_example(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "LEO_URL": "https://leo.test",
        "LEO_API_URL": "https://leo.test/api/v1",
        "APP_CLIENT_ID": "miapp",
        "APP_CLIENT_SECRET": "fake-secret",
        "PUBLIC_URL": "https://miapp.test",
    }.items():
        monkeypatch.setenv(key, value)
    module = importlib.import_module("examples.minimal_app")
    module.auth.check_catalog()
    assert module.auth.used_tags == {"miapp.things.view", "miapp.things.edit"}
