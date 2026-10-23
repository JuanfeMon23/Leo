"""Hash y politica de contrasenas (argon2id).

`argon2-cffi` (`PasswordHasher`) usa por defecto argon2id con el perfil
RFC 9106 "low memory"; el hash guardado es el string PHC completo
(`$argon2id$v=19$m=...,t=...,p=...$<sal>$<hash>`), que incluye parametros y
sal. Lo usan la semilla del administrador y, despues, el modulo `users`.
"""

from functools import lru_cache
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from leo_sdk.models import PasswordPolicy as SdkPasswordPolicy
from pydantic import model_validator

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()


class PasswordPolicy(SdkPasswordPolicy):
    """Politica de contrasenas. Las reglas viven en `leo_sdk.models`; aqui solo
    se fija el piso/techo de codigo: los ajustes (`password.*`) pueden subir el
    minimo o relajar las clases de caracteres, pero la longitud siempre queda
    entre `MIN_PASSWORD_LENGTH` y `MAX_PASSWORD_LENGTH`."""

    @model_validator(mode="before")
    @classmethod
    def _clamp_length(cls, data: Any) -> Any:
        if isinstance(data, dict):
            minimum = data.get("min_length", MIN_PASSWORD_LENGTH)
            data = {
                **data,
                "min_length": max(
                    MIN_PASSWORD_LENGTH, min(minimum, MAX_PASSWORD_LENGTH)
                ),
                "max_length": MAX_PASSWORD_LENGTH,
            }
        return data


DEFAULT_POLICY = PasswordPolicy()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True si el hash se hizo con parametros distintos a los actuales
    (se recalcula al siguiente login correcto)."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _hasher.hash("leo-usuario-inexistente")


def burn_verification_time(password: str) -> None:
    """Verifica contra un hash ficticio: el login de un usuario inexistente
    tarda lo mismo que el de uno existente (no revela si existe)."""
    verify_password(_dummy_hash(), password)


_MESSAGES = {
    "no_lowercase": "debe incluir una minúscula",
    "no_uppercase": "debe incluir una mayúscula",
    "no_digit": "debe incluir un dígito",
    "no_symbol": "debe incluir un símbolo",
}


def password_weaknesses(
    password: str,
    *,
    username: str | None = None,
    email: str | None = None,
    policy: PasswordPolicy = DEFAULT_POLICY,
) -> list[str]:
    """Motivos (en espanol) por los que la contrasena es debil; [] si es fuerte.

    Por defecto fuerte = 12-128 caracteres, con minuscula, mayuscula, digito y
    simbolo; `policy` (de los ajustes `password.*`) puede subir el minimo o
    quitar clases, nunca bajar de 12. Decision del usuario (2026-10-22): se
    permite que contenga el usuario o la parte local del email; `username` y
    `email` se conservan en la firma por compatibilidad con los llamadores, pero
    ya no entran en la politica.
    """
    codes = policy.check(password)
    problems = []
    if "too_short" in codes or "too_long" in codes:
        problems.append(
            f"debe tener entre {policy.min_length} y {policy.max_length} caracteres"
        )
    problems.extend(_MESSAGES[code] for code in codes if code in _MESSAGES)
    return problems
