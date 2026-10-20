"""Verificacion de pruebas DPoP (RFC 9449) en el BFF: ES256 / P-256.

El servidor de Leo no ve la prueba del navegador en `/token`, `/introspect` ni
`/revoke`: la verifica el backend de la app con este modulo y le pasa a Leo el
`jkt`. Se comprueba, en este orden: formato JWS compacto y tamano; header
(`typ = dpop+jwt`, `alg = ES256` unico permitido, `jwk` publico EC P-256 sin
miembros privados y punto en la curva); firma; claims (`htm`, `htu` exacta sin
query ni fragmento, `iat` +-60 s, `jti`); y solo entonces el `jti` se registra
en el `ReplayStore` (una prueba rechazada no lo quema).

Implementado con `cryptography` (PyCA), sin libreria JOSE: un solo algoritmo, sin
negociacion atacable.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from leo_sdk.crypto import b64url_decode, jwk_thumbprint

DPOP_HEADER = "DPoP"
DPOP_TYP = "dpop+jwt"
DPOP_ALG = "ES256"
IAT_LEEWAY_SECONDS = 60
REPLAY_TTL_SECONDS = 2 * IAT_LEEWAY_SECONDS + 5
MAX_PROOF_LENGTH = 4096
MAX_JTI_LENGTH = 256
_ALLOWED_JWK_MEMBERS = {"kty", "crv", "x", "y", "alg", "use", "kid", "key_ops", "ext"}
_COORD_BYTES = 32


class DpopError(Exception):
    """Prueba DPoP invalida. `reason` es tecnico (logs/tests)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class DpopProof:
    jkt: str
    jti: str
    htm: str
    htu: str
    iat: int


class ReplayStore(Protocol):
    """Almacen anti-replay de `jti`. Con varias instancias del BFF debe ser
    compartido (Redis, tabla con TTL): `InMemoryReplayStore` solo protege
    dentro de un proceso (pendiente documentado)."""

    async def add_if_new(self, key: str, ttl_seconds: float) -> bool:
        """True si `key` no estaba (queda registrada `ttl_seconds`); False si es
        un replay."""
        ...


class InMemoryReplayStore:
    def __init__(
        self, clock: Callable[[], float] = time.monotonic, max_entries: int = 10_000
    ) -> None:
        self._clock = clock
        self._max = max_entries
        self._seen: dict[str, float] = {}

    async def add_if_new(self, key: str, ttl_seconds: float) -> bool:
        now = self._clock()
        if len(self._seen) >= self._max:
            self._seen = {k: e for k, e in self._seen.items() if e > now}
        expires = self._seen.get(key)
        if expires is not None and expires > now:
            return False
        self._seen[key] = now + ttl_seconds
        return True


def expected_htu(public_url: str, path: str) -> str:
    """`htu` esperado: esquema + host (+ puerto no estandar) de `public_url` y
    `path`, sin query ni fragmento."""
    parts = urlsplit(public_url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    default = {"http": 80, "https": 443}.get(scheme)
    netloc = host if parts.port in (None, default) else f"{host}:{parts.port}"
    base_path = parts.path.rstrip("/")
    return f"{scheme}://{netloc}{base_path}{path.split('?')[0].split('#')[0]}"


def _json_segment(segment: str, what: str) -> dict:
    try:
        value = json.loads(b64url_decode(segment))
    except (ValueError, UnicodeDecodeError) as exc:
        raise DpopError(f"{what} no es JSON base64url valido") from exc
    if not isinstance(value, dict):
        raise DpopError(f"{what} no es un objeto JSON")
    return value


def _public_key(jwk: object) -> ec.EllipticCurvePublicKey:
    if not isinstance(jwk, dict):
        raise DpopError("falta jwk en el header")
    if set(jwk) - _ALLOWED_JWK_MEMBERS:
        raise DpopError("el jwk contiene miembros no permitidos (privados)")
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise DpopError("el jwk no es EC P-256")
    try:
        x = b64url_decode(jwk.get("x", ""))
        y = b64url_decode(jwk.get("y", ""))
    except ValueError as exc:
        raise DpopError("coordenadas del jwk invalidas") from exc
    if len(x) != _COORD_BYTES or len(y) != _COORD_BYTES:
        raise DpopError("coordenadas del jwk invalidas")
    try:
        return ec.EllipticCurvePublicNumbers(
            int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()
        ).public_key()
    except ValueError as exc:
        raise DpopError("el jwk no es un punto valido de P-256") from exc


def _verify_signature(
    key: ec.EllipticCurvePublicKey, signing_input: bytes, signature_b64: str
) -> None:
    try:
        raw = b64url_decode(signature_b64)
    except ValueError as exc:
        raise DpopError("firma no es base64url") from exc
    if len(raw) != 2 * _COORD_BYTES:
        raise DpopError("firma ES256 con longitud invalida")
    der = encode_dss_signature(
        int.from_bytes(raw[:_COORD_BYTES], "big"),
        int.from_bytes(raw[_COORD_BYTES:], "big"),
    )
    try:
        key.verify(der, signing_input, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise DpopError("firma invalida") from exc


def check_dpop_proof(
    proof: str | None, *, htm: str, htu: str, now: float | None = None
) -> DpopProof:
    """Validacion completa SIN anti-replay (`DpopError` si algo falla)."""
    now = time.time() if now is None else now
    if not proof:
        raise DpopError("falta la prueba DPoP")
    if len(proof) > MAX_PROOF_LENGTH:
        raise DpopError("prueba DPoP demasiado grande")
    parts = proof.split(".")
    if len(parts) != 3:
        raise DpopError("la prueba DPoP no es un JWS compacto")
    header_b64, payload_b64, signature_b64 = parts

    header = _json_segment(header_b64, "header")
    if header.get("typ") != DPOP_TYP:
        raise DpopError("typ distinto de dpop+jwt")
    if header.get("alg") != DPOP_ALG:
        raise DpopError("alg no permitido (solo ES256)")
    key = _public_key(header.get("jwk"))
    _verify_signature(key, f"{header_b64}.{payload_b64}".encode("ascii"), signature_b64)

    claims = _json_segment(payload_b64, "payload")
    claim_htm, claim_htu = claims.get("htm"), claims.get("htu")
    if not isinstance(claim_htm, str) or claim_htm != htm.upper():
        raise DpopError("htm no coincide")
    if not isinstance(claim_htu, str) or claim_htu != htu:
        raise DpopError("htu no coincide")
    iat = claims.get("iat")
    if isinstance(iat, bool) or not isinstance(iat, int | float):
        raise DpopError("iat ausente o invalido")
    if abs(now - iat) > IAT_LEEWAY_SECONDS:
        raise DpopError("iat fuera de la ventana permitida")
    jti = claims.get("jti")
    if not isinstance(jti, str) or not 0 < len(jti) <= MAX_JTI_LENGTH:
        raise DpopError("jti ausente o invalido")
    return DpopProof(
        jkt=jwk_thumbprint(header["jwk"]),
        jti=jti,
        htm=claim_htm,
        htu=claim_htu,
        iat=int(iat),
    )


async def verify_dpop_proof(
    proof: str | None,
    *,
    htm: str,
    htu: str,
    store: ReplayStore,
    now: float | None = None,
) -> DpopProof:
    """`check_dpop_proof` + registro del `jti` (anti-replay)."""
    result = check_dpop_proof(proof, htm=htm, htu=htu, now=now)
    if not await store.add_if_new(f"{result.jkt}:{result.jti}", REPLAY_TTL_SECONDS):
        raise DpopError("jti repetido (replay)")
    return result
