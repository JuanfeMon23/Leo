"""Hash y politica de contrasenas (argon2id).

`argon2-cffi` (`PasswordHasher`) usa por defecto argon2id con el perfil
RFC 9106 "low memory"; el hash guardado es el string PHC completo
(`$argon2id$v=19$m=...,t=...,p=...$<sal>$<hash>`), que incluye parametros y
sal. Lo usan la semilla del administrador y, despues, el modulo `users`.
"""

from dataclasses import dataclass
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()


@dataclass(frozen=True)
class PasswordPolicy:
    """Politica de contrasenas. Los ajustes (`password.*`) pueden subir el
    minimo o relajar las clases de caracteres, pero la longitud siempre queda
    entre `MIN_PASSWORD_LENGTH` y `MAX_PASSWORD_LENGTH` (piso/techo de codigo)."""

    min_length: int = MIN_PASSWORD_LENGTH
    max_length: int = MAX_PASSWORD_LENGTH
    require_lowercase: bool = True
    require_uppercase: bool = True
    require_digit: bool = True
    require_symbol: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "min_length",
            max(MIN_PASSWORD_LENGTH, min(self.min_length, MAX_PASSWORD_LENGTH)),
        )
        object.__setattr__(self, "max_length", MAX_PASSWORD_LENGTH)


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
    problems = []
    if not policy.min_length <= len(password) <= policy.max_length:
        problems.append(
            f"debe tener entre {policy.min_length} y {policy.max_length} caracteres"
        )
    if policy.require_lowercase and not any(c.islower() for c in password):
        problems.append("debe incluir una minúscula")
    if policy.require_uppercase and not any(c.isupper() for c in password):
        problems.append("debe incluir una mayúscula")
    if policy.require_digit and not any(c.isdigit() for c in password):
        problems.append("debe incluir un dígito")
    if policy.require_symbol and all(c.isalnum() for c in password):
        problems.append("debe incluir un símbolo")
    return problems
