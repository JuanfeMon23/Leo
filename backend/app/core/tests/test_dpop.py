"""Verificacion DPoP (RFC 9449): caso valido y los ataques que debe frenar
(regla 4 de AGENTS.md: ningun cambio de seguridad sin test del ataque)."""

import hashlib
import hmac
import json
from datetime import timedelta

import pytest

from app.core import clock
from app.core.crypto import b64url_encode
from app.core.dpop import DpopError, JtiReplayCache, verify_dpop_proof

from .dpop_keys import DpopKey, _b64json

HTU = "https://leo.example/api/v1/auth/me"


@pytest.fixture
def key() -> DpopKey:
    return DpopKey()


@pytest.fixture
def cache() -> JtiReplayCache:
    return JtiReplayCache()


def verify(proof: str, cache: JtiReplayCache, **overrides: object):
    kwargs: dict = {"htm": "GET", "htu": HTU, "now": clock.now(), "cache": cache}
    kwargs.update(overrides)
    return verify_dpop_proof(proof, **kwargs)


def rejected(proof: str | None, cache: JtiReplayCache, **overrides: object) -> str:
    with pytest.raises(DpopError) as info:
        verify(proof, cache, **overrides)  # type: ignore[arg-type]
    return info.value.reason


def test_prueba_valida_devuelve_el_jkt_de_la_llave(key, cache) -> None:
    result = verify(key.proof("GET", HTU), cache)
    assert result.jkt == key.jkt
    assert len(result.jkt) == 43


def test_thumbprint_rfc7638_coincide_con_el_vector_del_rfc() -> None:
    # RFC 7638 seccion 3.1 usa RSA; para EC se verifica la forma canonica.
    from app.core.dpop import jwk_thumbprint

    jwk = {"kty": "EC", "crv": "P-256", "x": "AAA", "y": "BBB", "kid": "ignorado"}
    canonical = b'{"crv":"P-256","kty":"EC","x":"AAA","y":"BBB"}'
    expected = b64url_encode(hashlib.sha256(canonical).digest())
    assert jwk_thumbprint(jwk) == expected


def test_sin_prueba_se_rechaza(cache) -> None:
    assert rejected(None, cache) == "falta la prueba DPoP"


def test_firma_invalida_se_rechaza(key, cache) -> None:
    proof = key.proof("GET", HTU)
    head, payload, sig = proof.split(".")
    tampered = _b64json({**json.loads(_decode(payload)), "htm": "GET", "x": 1})
    assert rejected(f"{head}.{tampered}.{sig}", cache) == "firma invalida"


def test_firmada_con_otra_llave_se_rechaza(key, cache) -> None:
    thief = DpopKey()
    # Header con la llave publica de la victima, firma con la del atacante.
    assert rejected(key.proof("GET", HTU, signer=thief), cache) == "firma invalida"


def test_otra_llave_valida_produce_otro_jkt(key, cache) -> None:
    other = DpopKey()
    assert verify(other.proof("GET", HTU), cache).jkt != key.jkt


def test_htm_cambiado_se_rechaza(key, cache) -> None:
    assert rejected(key.proof("POST", HTU), cache) == "htm no coincide"


def test_htu_cambiado_se_rechaza(key, cache) -> None:
    other = "https://leo.example/api/v1/users"
    assert rejected(key.proof("GET", other), cache) == "htu no coincide"


def test_htu_con_query_se_rechaza(key, cache) -> None:
    assert rejected(key.proof("GET", HTU + "?a=1"), cache) == "htu no coincide"


def test_iat_viejo_se_rechaza(key, cache) -> None:
    old = clock.now() - timedelta(seconds=61)
    assert rejected(key.proof("GET", HTU, iat=old), cache) == (
        "iat fuera de la ventana permitida"
    )


def test_iat_futuro_se_rechaza(key, cache) -> None:
    future = clock.now() + timedelta(seconds=61)
    assert rejected(key.proof("GET", HTU, iat=future), cache) == (
        "iat fuera de la ventana permitida"
    )


def test_iat_dentro_de_la_ventana_se_acepta(key, cache) -> None:
    near = clock.now() - timedelta(seconds=50)
    assert verify(key.proof("GET", HTU, iat=near), cache).jkt == key.jkt


def test_jti_repetido_se_rechaza(key, cache) -> None:
    proof = key.proof("GET", HTU)
    verify(proof, cache)
    assert rejected(proof, cache) == "jti repetido (replay)"


def test_prueba_invalida_no_consume_el_jti(key, cache) -> None:
    rejected(key.proof("POST", HTU, jti="j-1"), cache)
    assert verify(key.proof("GET", HTU, jti="j-1"), cache).jti == "j-1"


def test_sin_jti_se_rechaza(key, cache) -> None:
    assert rejected(key.proof("GET", HTU, claims={"jti": None}), cache) == (
        "jti ausente o invalido"
    )


def test_alg_none_se_rechaza(key, cache) -> None:
    head = _b64json({"typ": "dpop+jwt", "alg": "none", "jwk": key.public_jwk})
    payload = _b64json(
        {"htm": "GET", "htu": HTU, "iat": int(clock.now().timestamp()), "jti": "n"}
    )
    assert rejected(f"{head}.{payload}.", cache) == "alg no permitido (solo ES256)"


def test_alg_hs256_con_la_llave_publica_como_secreto_se_rechaza(key, cache) -> None:
    head = _b64json({"typ": "dpop+jwt", "alg": "HS256", "jwk": key.public_jwk})
    payload = _b64json(
        {"htm": "GET", "htu": HTU, "iat": int(clock.now().timestamp()), "jti": "h"}
    )
    secret = json.dumps(key.public_jwk).encode()
    mac = hmac.new(secret, f"{head}.{payload}".encode(), hashlib.sha256).digest()
    assert rejected(f"{head}.{payload}.{b64url_encode(mac)}", cache) == (
        "alg no permitido (solo ES256)"
    )


def test_jwk_con_parte_privada_se_rechaza(key, cache) -> None:
    private = key.private_key.private_numbers().private_value.to_bytes(32, "big")
    jwk = {**key.public_jwk, "d": b64url_encode(private)}
    assert rejected(key.proof("GET", HTU, header={"jwk": jwk}), cache) == (
        "el jwk contiene miembros no permitidos (privados)"
    )


def test_typ_distinto_se_rechaza(key, cache) -> None:
    assert rejected(key.proof("GET", HTU, header={"typ": "JWT"}), cache) == (
        "typ distinto de dpop+jwt"
    )


def test_jwk_que_no_es_p256_se_rechaza(key, cache) -> None:
    jwk = {**key.public_jwk, "crv": "P-384"}
    assert rejected(key.proof("GET", HTU, header={"jwk": jwk}), cache) == (
        "el jwk no es EC P-256"
    )


def test_punto_fuera_de_la_curva_se_rechaza(key, cache) -> None:
    jwk = {**key.public_jwk, "y": b64url_encode((1).to_bytes(32, "big"))}
    assert rejected(key.proof("GET", HTU, header={"jwk": jwk}), cache) == (
        "el jwk no es un punto valido de P-256"
    )


def test_basura_se_rechaza(cache) -> None:
    assert rejected("no-es-un-jws", cache) == "la prueba DPoP no es un JWS compacto"


def test_ath_debe_coincidir_con_el_access_token(key, cache) -> None:
    proof = key.proof("GET", HTU, access_token="token-a")
    assert verify(proof, cache, access_token="token-a").jkt == key.jkt
    other = key.proof("GET", HTU, access_token="token-a")
    assert rejected(other, cache, access_token="token-b") == (
        "ath no coincide con el access token"
    )


def _decode(segment: str) -> bytes:
    from app.core.crypto import b64url_decode

    return b64url_decode(segment)
