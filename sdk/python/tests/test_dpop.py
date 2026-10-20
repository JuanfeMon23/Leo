"""Verificacion DPoP en el BFF, con sus casos de ataque."""

import hashlib
import hmac

import pytest

from leo_sdk.crypto import b64url_encode, jwk_thumbprint
from leo_sdk.dpop import (
    DpopError,
    InMemoryReplayStore,
    check_dpop_proof,
    expected_htu,
    verify_dpop_proof,
)
from tests.helpers import DpopKey, b64json

HTU = "https://app.test/api/things"
NOW = 1_800_000_000.0


def check(proof: str | None, *, htm: str = "GET", htu: str = HTU, now: float = NOW):
    return check_dpop_proof(proof, htm=htm, htu=htu, now=now)


def test_valid_proof_returns_jkt() -> None:
    key = DpopKey()
    result = check(key.proof("GET", HTU, iat=NOW))
    assert result.jkt == key.jkt
    assert len(result.jkt) == 43


def test_thumbprint_is_canonical_and_ignores_extra_members() -> None:
    a = {"kty": "EC", "crv": "P-256", "x": "AQ", "y": "Ag", "kid": "k"}
    b = {"y": "Ag", "x": "AQ", "crv": "P-256", "kty": "EC"}
    assert jwk_thumbprint(a) == jwk_thumbprint(b)


def test_wrong_signature_other_key() -> None:
    key, other = DpopKey(), DpopKey()
    with pytest.raises(DpopError, match="firma"):
        check(key.proof("GET", HTU, iat=NOW, signer=other))


def test_tampered_payload_breaks_signature() -> None:
    key = DpopKey()
    head, _payload, sig = key.proof("GET", HTU, iat=NOW).split(".")
    forged = b64json({"htm": "GET", "htu": HTU, "iat": int(NOW), "jti": "x"})
    with pytest.raises(DpopError, match="firma"):
        check(f"{head}.{forged}.{sig}")


def test_header_key_differs_from_signer() -> None:
    key, attacker = DpopKey(), DpopKey()
    proof = attacker.proof(
        "GET", HTU, iat=NOW, header={"jwk": key.public_jwk}, signer=attacker
    )
    with pytest.raises(DpopError, match="firma"):
        check(proof)


@pytest.mark.parametrize(
    ("htm", "htu"),
    [
        ("POST", HTU),
        ("GET", "https://app.test/api/other"),
        ("GET", "https://evil.test/api/things"),
        ("GET", HTU + "?x=1"),
        ("GET", HTU + "#frag"),
        ("GET", "http://app.test/api/things"),
    ],
)
def test_htm_htu_mismatch(htm: str, htu: str) -> None:
    key = DpopKey()
    with pytest.raises(DpopError, match="ht[mu]"):
        check(key.proof(htm, htu, iat=NOW))


def test_expected_method_is_case_insensitive() -> None:
    assert check(DpopKey().proof("GET", HTU, iat=NOW), htm="get")


@pytest.mark.parametrize("delta", [-61, 61, -3600, 3600])
def test_iat_outside_window(delta: int) -> None:
    with pytest.raises(DpopError, match="iat"):
        check(DpopKey().proof("GET", HTU, iat=NOW + delta))


@pytest.mark.parametrize("delta", [-60, 0, 60])
def test_iat_edges_ok(delta: int) -> None:
    assert check(DpopKey().proof("GET", HTU, iat=NOW + delta))


@pytest.mark.parametrize("iat", ["now", True, None])
def test_iat_must_be_number(iat: object) -> None:
    with pytest.raises(DpopError, match="iat"):
        check(DpopKey().proof("GET", HTU, iat=NOW, claims={"iat": iat}))


async def test_jti_replay_is_rejected() -> None:
    key, store = DpopKey(), InMemoryReplayStore()
    proof = key.proof("GET", HTU, iat=NOW, jti="same")
    kwargs = {"htm": "GET", "htu": HTU, "now": NOW, "store": store}
    assert await verify_dpop_proof(proof, **kwargs)
    with pytest.raises(DpopError, match="replay"):
        await verify_dpop_proof(proof, **kwargs)


async def test_failed_proof_does_not_burn_jti() -> None:
    key, store = DpopKey(), InMemoryReplayStore()
    bad = key.proof("POST", HTU, iat=NOW, jti="j1")
    good = key.proof("GET", HTU, iat=NOW, jti="j1")
    kwargs = {"htu": HTU, "now": NOW, "store": store}
    with pytest.raises(DpopError):
        await verify_dpop_proof(bad, htm="GET", **kwargs)
    assert await verify_dpop_proof(good, htm="GET", **kwargs)


async def test_same_jti_other_key_is_not_replay() -> None:
    store = InMemoryReplayStore()
    kwargs = {"htm": "GET", "htu": HTU, "now": NOW, "store": store}
    await verify_dpop_proof(DpopKey().proof("GET", HTU, iat=NOW, jti="j"), **kwargs)
    await verify_dpop_proof(DpopKey().proof("GET", HTU, iat=NOW, jti="j"), **kwargs)


async def test_replay_entry_expires() -> None:
    clock = [0.0]
    store = InMemoryReplayStore(clock=lambda: clock[0])
    assert await store.add_if_new("k", ttl_seconds=10)
    assert not await store.add_if_new("k", ttl_seconds=10)
    clock[0] = 11
    assert await store.add_if_new("k", ttl_seconds=10)


@pytest.mark.parametrize("alg", ["none", "HS256", "RS256", "ES384", "es256"])
def test_alg_other_than_es256(alg: str) -> None:
    with pytest.raises(DpopError, match="alg"):
        check(DpopKey().proof("GET", HTU, iat=NOW, header={"alg": alg}))


def test_alg_none_with_empty_signature() -> None:
    key = DpopKey()
    head = b64json({"typ": "dpop+jwt", "alg": "none", "jwk": key.public_jwk})
    body = b64json({"htm": "GET", "htu": HTU, "iat": int(NOW), "jti": "a"})
    with pytest.raises(DpopError, match="alg"):
        check(f"{head}.{body}.")


def test_hs256_mac_with_known_secret() -> None:
    key = DpopKey()
    head = b64json({"typ": "dpop+jwt", "alg": "HS256", "jwk": key.public_jwk})
    body = b64json({"htm": "GET", "htu": HTU, "iat": int(NOW), "jti": "a"})
    mac = hmac.new(b"secret", f"{head}.{body}".encode(), hashlib.sha256).digest()
    with pytest.raises(DpopError, match="alg"):
        check(f"{head}.{body}.{b64url_encode(mac)}")


def test_typ_must_be_dpop_jwt() -> None:
    with pytest.raises(DpopError, match="typ"):
        check(DpopKey().proof("GET", HTU, iat=NOW, header={"typ": "JWT"}))


def test_jwk_with_private_member_d() -> None:
    key = DpopKey()
    d = b64url_encode(
        key.private_key.private_numbers().private_value.to_bytes(32, "big")
    )
    jwk = {**key.public_jwk, "d": d}
    with pytest.raises(DpopError, match="privados"):
        check(key.proof("GET", HTU, iat=NOW, header={"jwk": jwk}))


def test_jwk_point_not_on_curve() -> None:
    key = DpopKey()
    bad = {**key.public_jwk, "y": b64url_encode((12345).to_bytes(32, "big"))}
    with pytest.raises(DpopError, match="punto"):
        check(key.proof("GET", HTU, iat=NOW, header={"jwk": bad}))


@pytest.mark.parametrize(
    "jwk",
    [
        None,
        "x",
        {"kty": "RSA", "n": "AQ", "e": "AQ"},
        {"kty": "EC", "crv": "P-384", "x": "AQ", "y": "AQ"},
        {"kty": "EC", "crv": "P-256", "x": "AQ", "y": "AQ"},
    ],
)
def test_malformed_jwk(jwk: object) -> None:
    with pytest.raises(DpopError):
        check(DpopKey().proof("GET", HTU, iat=NOW, header={"jwk": jwk}))


@pytest.mark.parametrize(
    "proof", [None, "", "a.b", "a.b.c.d", "x" * 5000, "!!!.???.***"]
)
def test_garbage_proofs(proof: str | None) -> None:
    with pytest.raises(DpopError):
        check(proof)


def test_signature_wrong_length() -> None:
    head, payload, _ = DpopKey().proof("GET", HTU, iat=NOW).split(".")
    with pytest.raises(DpopError, match="longitud"):
        check(f"{head}.{payload}.{b64url_encode(b'x' * 10)}")


def test_missing_jti() -> None:
    with pytest.raises(DpopError, match="jti"):
        check(DpopKey().proof("GET", HTU, iat=NOW, claims={"jti": ""}))


def test_expected_htu_normalizes() -> None:
    assert expected_htu("https://App.test:443/", "/a/b") == "https://app.test/a/b"
    assert expected_htu("http://localhost:8200", "/x") == "http://localhost:8200/x"
