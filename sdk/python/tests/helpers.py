"""Helpers de tests: llave DPoP de un "navegador" y fabrica de pruebas."""

import json
import time
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from leo_sdk.crypto import b64url_encode, jwk_thumbprint


def b64json(value: dict[str, Any]) -> str:
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
        iat: float | None = None,
        jti: str | None = None,
        header: dict[str, Any] | None = None,
        claims: dict[str, Any] | None = None,
        signer: "DpopKey | None" = None,
    ) -> str:
        """Prueba firmada; `header`/`claims` se mezclan (para manipularlos) y
        `signer` firma con otra llave."""
        payload: dict[str, Any] = {
            "htm": htm,
            "htu": htu,
            "iat": int(time.time() if iat is None else iat),
            "jti": jti or uuid4().hex,
        }
        payload.update(claims or {})
        head = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self.public_jwk}
        head.update(header or {})
        signing_input = f"{b64json(head)}.{b64json(payload)}"
        signature = (signer or self).sign(signing_input.encode("ascii"))
        return f"{signing_input}.{signature}"
