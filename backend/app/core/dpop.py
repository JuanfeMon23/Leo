"""Verificacion de pruebas DPoP (RFC 9449) con ES256 / P-256.

Implementada sobre `cryptography` (PyCA) directamente, sin libreria JOSE: el
unico JWS que Leo verifica es la prueba DPoP con un solo algoritmo (ES256),
asi que la superficie es minima y no hay negociacion de algoritmos que
atacar (`alg: none`, HS256 con la llave publica como secreto, etc.).

Comprueba, en este orden:
1. Formato JWS compacto, tamano maximo y JSON valido.
2. Header: `typ = dpop+jwt`, `alg = ES256` (unico permitido), `jwk` publico
   EC P-256 (sin `d` ni otros miembros privados), punto valido en la curva.
3. Firma ES256 sobre `header.payload` con esa llave.
4. Claims: `htm` = metodo, `htu` = URL esperada (sin query ni fragmento),
   `iat` dentro de +-`IAT_LEEWAY_SECONDS`, `jti` presente y no repetido, y
   `ath` = SHA-256 del access token cuando se pasa uno.
5. Solo si todo lo anterior pasa, registra el `jti` (anti-replay).

El resultado expone `jkt`: thumbprint RFC 7638 de la llave publica, que es lo
que queda atado a la sesion y a los tokens.
"""

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from app.core.crypto import (
    b64url_decode,
    b64url_encode,
    constant_time_equals,
    sha256_b64url,
)

DPOP_HEADER = "DPoP"
DPOP_TYP = "dpop+jwt"
DPOP_ALG = "ES256"
IAT_LEEWAY_SECONDS = 60
MAX_PROOF_LENGTH = 4096
MAX_JTI_LENGTH = 256
# Miembros permitidos en el `jwk` del header (todos publicos). Cualquier otro
# (p. ej. `d`, la parte privada) invalida la prueba.
_ALLOWED_JWK_MEMBERS = {"kty", "crv", "x", "y", "alg", "use", "kid", "key_ops", "ext"}
_COORD_BYTES = 32


class DpopError(Exception):
    """Prueba DPoP invalida. `reason` es tecnico (logs/tests); el mensaje al
    usuario lo pone quien la traduce a HTTP."""

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


class JtiReplayCache:
    """Cache anti-replay de `jti` con TTL, en memoria del proceso.

    Pendiente: con varias instancias del backend debe ser compartida (Redis o
    tabla con TTL); en memoria solo protege dentro de un proceso.
    """

    def __init__(self, ttl_seconds: int = 2 * IAT_LEEWAY_SECONDS + 5) -> None:
        self._ttl = ttl_seconds
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def add_if_new(self, key: str) -> bool:
        """True si `key` no estaba (y queda registrada); False si es replay."""
        now = time.monotonic()
        with self._lock:
            if len(self._seen) > 10_000:
                self._purge(now)
            expires = self._seen.get(key)
            if expires is not None and expires > now:
                return False
            self._seen[key] = now + self._ttl
            return True

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()

    def _purge(self, now: float) -> None:
        for key in [k for k, exp in self._seen.items() if exp <= now]:
            del self._seen[key]


replay_cache = JtiReplayCache()
"""Cache global del proceso (la usan las dependencias de `auth`)."""


def jwk_thumbprint(jwk: dict) -> str:
    """Thumbprint RFC 7638 (SHA-256, base64url) de una llave EC publica."""
    canonical = json.dumps(
        {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"], "y": jwk["y"]},
        separators=(",", ":"),
        sort_keys=True,
    )
    return b64url_encode(hashlib.sha256(canonical.encode("utf-8")).digest())


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
    except ValueError as exc:  # punto fuera de la curva
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


def verify_dpop_proof(
    proof: str | None,
    *,
    htm: str,
    htu: str,
    now: datetime,
    cache: JtiReplayCache,
    access_token: str | None = None,
) -> DpopProof:
    """Verifica la prueba y registra su `jti`; `DpopError` si algo falla."""
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
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    _verify_signature(key, signing_input, signature_b64)

    claims = _json_segment(payload_b64, "payload")
    claim_htm, claim_htu = claims.get("htm"), claims.get("htu")
    if not isinstance(claim_htm, str) or claim_htm != htm.upper():
        raise DpopError("htm no coincide")
    if not isinstance(claim_htu, str) or claim_htu != htu:
        raise DpopError("htu no coincide")
    iat = claims.get("iat")
    if isinstance(iat, bool) or not isinstance(iat, int | float):
        raise DpopError("iat ausente o invalido")
    if abs(now.timestamp() - iat) > IAT_LEEWAY_SECONDS:
        raise DpopError("iat fuera de la ventana permitida")
    jti = claims.get("jti")
    if not isinstance(jti, str) or not 0 < len(jti) <= MAX_JTI_LENGTH:
        raise DpopError("jti ausente o invalido")
    if access_token is not None:
        ath = claims.get("ath")
        if not isinstance(ath, str) or not constant_time_equals(
            ath, sha256_b64url(access_token)
        ):
            raise DpopError("ath no coincide con el access token")

    jkt = jwk_thumbprint(header["jwk"])
    if not cache.add_if_new(f"{jkt}:{jti}"):
        raise DpopError("jti repetido (replay)")
    return DpopProof(jkt=jkt, jti=jti, htm=claim_htm, htu=claim_htu, iat=int(iat))
