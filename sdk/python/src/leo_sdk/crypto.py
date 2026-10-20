"""Utilidades criptograficas minimas (sin criptografia propia: `secrets`,
`hashlib` y `hmac` de la libreria estandar)."""

import base64
import hashlib
import hmac
import json
import secrets


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
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_b64url(value: str) -> str:
    return b64url_encode(hashlib.sha256(value.encode("utf-8")).digest())


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def random_token(nbytes: int = 32) -> str:
    """Valor aleatorio base64url (por defecto 256 bits, 43 caracteres)."""
    return b64url_encode(secrets.token_bytes(nbytes))


def jwk_thumbprint(jwk: dict) -> str:
    """Thumbprint RFC 7638 (SHA-256, base64url) de una llave EC publica."""
    canonical = json.dumps(
        {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"], "y": jwk["y"]},
        separators=(",", ":"),
        sort_keys=True,
    )
    return b64url_encode(hashlib.sha256(canonical.encode("utf-8")).digest())
