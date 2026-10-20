"""Helper de tests: llave DPoP de un "dispositivo" y fabrica de pruebas.

Imita lo que hace el navegador con WebCrypto (ES256/P-256): firma la prueba
JWS con su llave privada y publica solo la parte publica en el header. Cada
argumento de `proof()` permite fabricar una prueba manipulada para los tests
de ataque.
"""

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from app.core import clock
from app.core.crypto import b64url_encode, sha256_b64url
from app.core.dpop import jwk_thumbprint


def _b64json(value: dict[str, Any]) -> str:
    return b64url_encode(json.dumps(value, separators=(",", ":")).encode("utf-8"))


class DpopKey:
    def __init__(self) -> None:
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        numbers = self.private_key.public_key().public_numbers()
        self.public_jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": b64url_encode(numbers.x.to_bytes(32, "big")),
            "y": b64url_encode(numbers.y.to_bytes(32, "big")),
        }
        self.jkt = jwk_thumbprint(self.public_jwk)

    def sign(self, signing_input: bytes) -> str:
        der = self.private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

    def proof(
        self,
        htm: str,
        htu: str,
        *,
        iat: datetime | float | None = None,
        jti: str | None = None,
        access_token: str | None = None,
        header: dict[str, Any] | None = None,
        claims: dict[str, Any] | None = None,
        signer: "DpopKey | None" = None,
    ) -> str:
        """Prueba DPoP firmada. `header`/`claims` se mezclan sobre los valores
        correctos (para manipularlos); `signer` firma con OTRA llave."""
        when = clock.now() if iat is None else iat
        payload: dict[str, Any] = {
            "htm": htm,
            "htu": htu,
            "iat": int(when.timestamp()) if isinstance(when, datetime) else when,
            "jti": jti or uuid4().hex,
        }
        if access_token is not None:
            payload["ath"] = sha256_b64url(access_token)
        payload.update(claims or {})
        head = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self.public_jwk}
        head.update(header or {})
        signing_input = f"{_b64json(head)}.{_b64json(payload)}"
        signature = (signer or self).sign(signing_input.encode("ascii"))
        return f"{signing_input}.{signature}"
