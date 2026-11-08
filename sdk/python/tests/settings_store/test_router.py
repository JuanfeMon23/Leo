"""Router reutilizable: permisos inyectados, errores, auditoria."""

from types import SimpleNamespace
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from httpx import ASGITransport, AsyncClient

from leo_sdk.settings_store import (
    SettingsRouterDeps,
    SettingsStore,
    build_settings_router,
)

from .conftest import MODELS


def needs(perm: str):
    """Dependencia de permiso de prueba: `X-Perms: view,edit` (+ `X-User`)."""

    async def dep(
        x_perms: Annotated[str, Header()] = "",
        x_user: Annotated[str, Header()] = "ana",
    ):
        perms = x_perms.split(",")
        if perm not in perms:
            raise HTTPException(403, {"code": "forbidden"})
        return SimpleNamespace(
            user_id=None, username=x_user, meta=SimpleNamespace(request_id="rq-1")
        )

    return Depends(dep)


@pytest.fixture
def audit_calls():
    return []


@pytest.fixture
async def api(registry, shared_factory, clock, audit_calls):
    store = SettingsStore(registry, shared_factory, MODELS, monotonic=clock)
    await store.sync_registry()

    async def audit(actor, key, before, after, reason):
        audit_calls.append((actor.username, key, before, after, reason))

    app = FastAPI()
    app.include_router(
        build_settings_router(
            store,
            SettingsRouterDeps(
                view_dep=needs("view"),
                edit_dep=needs("edit"),
                edit_security_dep=needs("edit-security"),
                audit=audit,
            ),
        ),
        prefix="/settings",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as client:
        yield client


VIEW = {"X-Perms": "view"}
EDIT = {"X-Perms": "view,edit"}
SECURITY = {"X-Perms": "view,edit,edit-security"}


async def test_list_grouped_with_full_contract(api):
    response = await api.get("/settings", headers=VIEW)
    assert response.status_code == 200
    groups = response.json()["groups"]
    assert [group["group"] for group in groups] == ["auth", "ui"]
    item = next(
        setting
        for setting in groups[0]["settings"]
        if setting["key"] == "auth.max_attempts"
    )
    assert item == {
        "key": "auth.max_attempts",
        "type": "int",
        "value": 5,
        "default": 5,
        "min": 3,
        "max": 20,
        "unit": "count",
        "description": "Intentos antes del bloqueo.",
        "version": 1,
        "requires_security_permission": True,
        "updated_at": item["updated_at"],
        "updated_by": None,
        "updated_by_username": None,
    }


async def test_view_permission_required(api):
    assert (await api.get("/settings")).status_code == 403
    assert (await api.get("/settings/auth.idle_minutes/history")).status_code == 403
    assert (await api.get("/settings", headers={"X-Perms": "edit"})).status_code == 403


async def test_edit_requires_edit_permission(api):
    body = {"value": 45, "reason": "motivo", "expected_version": 1}
    response = await api.put("/settings/auth.idle_minutes", json=body, headers=VIEW)
    assert response.status_code == 403


async def test_edit_ok_audits_and_returns_new_state(api, audit_calls):
    body = {"value": 45, "reason": "Nueva política", "expected_version": 1}
    response = await api.put("/settings/auth.idle_minutes", json=body, headers=EDIT)
    assert response.status_code == 200, response.text
    assert (
        response.json()["value"],
        response.json()["version"],
        response.json()["updated_by_username"],
    ) == (
        45,
        2,
        "ana",
    )
    assert audit_calls == [("ana", "auth.idle_minutes", 30, 45, "Nueva política")]
    history_response = await api.get(
        "/settings/auth.idle_minutes/history", headers=VIEW
    )
    assert history_response.status_code == 200
    page = history_response.json()
    assert page["total"] == 1 and page["items"][0]["request_id"] == "rq-1"
    assert (page["items"][0]["old_value"], page["items"][0]["new_value"]) == (30, 45)


async def test_security_key_requires_third_permission(api, audit_calls):
    body = {"value": 6, "reason": "motivo", "expected_version": 1}
    response = await api.put("/settings/auth.max_attempts", json=body, headers=EDIT)
    assert response.status_code == 403 and audit_calls == []
    response = await api.put("/settings/auth.max_attempts", json=body, headers=SECURITY)
    assert response.status_code == 200 and response.json()["value"] == 6


async def test_errors_are_code_message_details(api, audit_calls):
    ok = {"value": 45, "reason": "motivo", "expected_version": 1}

    response = await api.put(
        "/settings/auth.idle_minutes", json={**ok, "value": 999}, headers=EDIT
    )
    assert response.status_code == 422
    assert response.json()["code"] == "setting_out_of_range"
    assert (
        response.json()["details"]["min"] == 5
        and response.json()["details"]["max"] == 120
    )
    assert "entre 5 y 120" in response.json()["message"]

    response = await api.put(
        "/settings/auth.idle_minutes", json={**ok, "value": "45"}, headers=EDIT
    )
    assert (response.status_code, response.json()["code"]) == (
        422,
        "setting_type_mismatch",
    )

    for reason in ("ab", "", None):
        response = await api.put(
            "/settings/auth.idle_minutes", json={**ok, "reason": reason}, headers=EDIT
        )
        assert (response.status_code, response.json()["code"]) == (
            422,
            "reason_required",
        )

    await api.put("/settings/auth.idle_minutes", json=ok, headers=EDIT)
    response = await api.put("/settings/auth.idle_minutes", json=ok, headers=EDIT)
    assert (response.status_code, response.json()["code"]) == (409, "version_conflict")
    assert response.json()["details"]["current_version"] == 2

    response = await api.put("/settings/no.existe", json=ok, headers=EDIT)
    assert (response.status_code, response.json()["code"]) == (404, "setting_not_found")
    response = await api.get("/settings/no.existe/history", headers=VIEW)
    assert (response.status_code, response.json()["code"]) == (404, "setting_not_found")

    response = await api.put(
        "/settings/auth.idle_minutes", json={"reason": "motivo"}, headers=EDIT
    )
    assert response.status_code == 422
    assert len(audit_calls) == 1  # solo el cambio valido


async def test_history_pagination(api):
    for version, value in enumerate([10, 11, 12], start=1):
        await api.put(
            "/settings/auth.idle_minutes",
            json={"value": value, "reason": "cambio", "expected_version": version},
            headers=EDIT,
        )
    response = await api.get(
        "/settings/auth.idle_minutes/history?page=2&page_size=2", headers=VIEW
    )
    assert response.json()["total"] == 3 and len(response.json()["items"]) == 1
    bad = await api.get("/settings/auth.idle_minutes/history?page=0", headers=VIEW)
    assert bad.status_code == 422
