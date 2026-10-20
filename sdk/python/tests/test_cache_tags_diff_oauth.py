"""Cache TTL, validacion de tags, diff de auditoria y state/PKCE."""

import pytest

from leo_sdk.audit import diff
from leo_sdk.cache import TTLCache
from leo_sdk.crypto import sha256_b64url
from leo_sdk.oauth import (
    FlowCookie,
    FlowCookieError,
    build_authorize_url,
    new_flow,
    pkce_challenge,
)
from leo_sdk.tags import InvalidTagError, validate_tag

# --- cache ---


def test_cache_expires_after_ttl() -> None:
    now = [100.0]
    cache: TTLCache[str] = TTLCache(30, clock=lambda: now[0])
    cache.set("k", "v")
    now[0] = 129.9
    assert cache.get("k") == "v"
    now[0] = 130.0
    assert cache.get("k") is None


def test_cache_delete_and_clear() -> None:
    cache: TTLCache[int] = TTLCache(30)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.delete("a")
    assert cache.get("a") is None
    cache.clear()
    assert cache.get("b") is None


def test_cache_is_bounded() -> None:
    now = [0.0]
    cache: TTLCache[int] = TTLCache(30, clock=lambda: now[0], max_entries=3)
    for i in range(10):
        cache.set(str(i), i)
    assert len(cache) <= 3
    assert cache.get("9") == 9


def test_cache_ttl_zero_disables() -> None:
    cache: TTLCache[int] = TTLCache(0)
    cache.set("a", 1)
    assert cache.get("a") is None


# --- tags ---


@pytest.mark.parametrize("tag", ["app.mod.view", "vladimir.samples.edit", "a-b.c-d.e1"])
def test_valid_tags(tag: str) -> None:
    assert validate_tag(tag) == tag


@pytest.mark.parametrize(
    "tag",
    [
        "",
        "app.mod",
        "app.mod.view.extra",
        "App.mod.view",
        "app..view",
        "app.mod.-v",
        "app.mod.v_w",
        "Evento: algo",
        "app.mod.view ",
        "-a.b.c",
    ],
)
def test_invalid_tags(tag: str) -> None:
    with pytest.raises(InvalidTagError):
        validate_tag(tag)


def test_tag_must_belong_to_app() -> None:
    assert validate_tag("app.mod.view", app_slug="app")
    with pytest.raises(InvalidTagError, match="aplicaci"):
        validate_tag("other.mod.view", app_slug="app")


# --- diff ---


def test_diff_only_changed_fields() -> None:
    result = diff({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 5, "d": 4})
    assert result == {
        "b": {"before": 2, "after": 5},
        "c": {"before": 3, "after": None},
        "d": {"before": None, "after": 4},
    }


def test_diff_never_includes_sensitive_fields() -> None:
    before = {
        "name": "a",
        "password": "x",
        "api_secret": "s",
        "Token": "t",
        "password_hash": "h",
        "refresh_token": "r",
    }
    after = {
        "name": "b",
        "password": "y",
        "api_secret": "s2",
        "Token": "t2",
        "password_hash": "h2",
        "refresh_token": "r2",
    }
    result = diff(before, after)
    assert result == {"name": {"before": "a", "after": "b"}}
    assert "x" not in str(result) and "y" not in str(result)


def test_diff_scrubs_nested_sensitive_values() -> None:
    result = diff({"cfg": {"a": 1, "secret": "s"}}, {"cfg": {"a": 2, "secret": "t"}})
    assert result == {"cfg": {"before": {"a": 1}, "after": {"a": 2}}}


def test_diff_custom_sensitive_list() -> None:
    result = diff({"pin": 1, "x": 1}, {"pin": 2, "x": 2}, sensitive=("pin",))
    assert result == {"x": {"before": 1, "after": 2}}


def test_diff_none_sides_and_json_safe() -> None:
    from datetime import date
    from uuid import UUID

    uid = UUID(int=1)
    created = diff(None, {"id": uid, "day": date(2026, 1, 2)})
    assert created == {
        "id": {"before": None, "after": str(uid)},
        "day": {"before": None, "after": "2026-01-02"},
    }
    assert diff({"a": 1}, {"a": 1}) == {}


# --- state / PKCE ---


def test_pkce_challenge_is_s256() -> None:
    assert pkce_challenge("v" * 43) == sha256_b64url("v" * 43)


def test_new_flow_generates_unique_values() -> None:
    a, b = new_flow(jkt="J" * 43), new_flow(jkt="J" * 43)
    assert a.state != b.state and a.code_verifier != b.code_verifier
    assert len(a.code_verifier) >= 43
    assert a.code_challenge == pkce_challenge(a.code_verifier)


def test_flow_cookie_roundtrip() -> None:
    cookie = FlowCookie(key=b"k" * 32, ttl_seconds=600, clock=lambda: 1000.0)
    flow = new_flow(jkt="J" * 43)
    value = cookie.dumps(flow)
    assert cookie.loads(value) == flow


@pytest.mark.parametrize("mutation", ["flip", "truncate", "empty", "garbage"])
def test_flow_cookie_tamper_detected(mutation: str) -> None:
    cookie = FlowCookie(key=b"k" * 32, clock=lambda: 1000.0)
    value = cookie.dumps(new_flow(jkt="J" * 43))
    bad = {
        "flip": value[:-2] + ("AA" if not value.endswith("AA") else "BB"),
        "truncate": value[:20],
        "empty": "",
        "garbage": "a.b",
    }[mutation]
    with pytest.raises(FlowCookieError):
        cookie.loads(bad)


def test_flow_cookie_other_key_rejected() -> None:
    value = FlowCookie(key=b"a" * 32, clock=lambda: 1.0).dumps(new_flow(jkt="J" * 43))
    with pytest.raises(FlowCookieError):
        FlowCookie(key=b"b" * 32, clock=lambda: 1.0).loads(value)


def test_flow_cookie_expires() -> None:
    now = [1000.0]
    cookie = FlowCookie(key=b"k" * 32, ttl_seconds=600, clock=lambda: now[0])
    value = cookie.dumps(new_flow(jkt="J" * 43))
    now[0] = 1601.0
    with pytest.raises(FlowCookieError, match="expir"):
        cookie.loads(value)


def test_authorize_url() -> None:
    flow = new_flow(jkt="J" * 43)
    url = build_authorize_url(
        "https://leo.test/",
        client_id="app",
        redirect_uri="https://a.test/cb",
        flow=flow,
    )
    assert url.startswith("https://leo.test/authorize?")
    for part in (
        "client_id=app",
        "redirect_uri=https%3A%2F%2Fa.test%2Fcb",
        f"state={flow.state}",
        f"code_challenge={flow.code_challenge}",
        "code_challenge_method=S256",
        f"dpop_jkt={'J' * 43}",
    ):
        assert part in url
    assert "code_verifier" not in url
