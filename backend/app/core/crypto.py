"""Utilidades criptograficas del nucleo (sin criptografia propia: `secrets`,
`hashlib` y `hmac` de la libreria estandar).

- Tokens opacos (access, refresh, code, cookie SSO, client_secret): 256 bits
  de `secrets.token_bytes`, codificados en base64url sin relleno (43 chars).
  En la BD solo va `sha256_hex(token)`; nunca el token.
- Comparaciones de secretos/hashes siempre en tiempo constante.
"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

TOKEN_BYTES = 32  # 256 bits


def b64url_encode(data: bytes) -> str:
    """base64url sin relleno (RFC 7515 / RFC 7636)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(data: str) -> bytes:
    """Decodifica base64url sin relleno; `ValueError` si no es valido."""
    if not isinstance(data, str) or "=" in data:
        raise ValueError("base64url invalido")
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError("base64url invalido") from exc
    if b64url_encode(raw) != data:  # rechaza alfabetos/bits sobrantes
        raise ValueError("base64url invalido")
    return raw


def sha256_hex(value: str) -> str:
    """SHA-256 en hex minuscula (formato `SHA256_HEX_PATTERN` de la BD)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_b64url(value: str) -> str:
    """SHA-256 en base64url sin relleno (43 chars): PKCE S256 y `ath`."""
    return b64url_encode(hashlib.sha256(value.encode("ascii")).digest())


def constant_time_equals(a: str, b: str) -> bool:
    """Comparacion en tiempo constante (no filtra el prefijo comun)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@dataclass(frozen=True)
class OpaqueToken:
    """Token recien generado: `value` va al cliente UNA vez, `hash` a la BD."""

    value: str
    hash: str


def new_opaque_token() -> OpaqueToken:
    value = b64url_encode(secrets.token_bytes(TOKEN_BYTES))
    return OpaqueToken(value=value, hash=sha256_hex(value))


def pkce_s256_matches(code_verifier: str, code_challenge: str) -> bool:
    """`BASE64URL(SHA256(verifier)) == challenge` (RFC 7636), tiempo constante."""
    return constant_time_equals(sha256_b64url(code_verifier), code_challenge)
