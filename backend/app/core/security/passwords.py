"""Hash y politica de contrasenas (argon2id).

`argon2-cffi` (`PasswordHasher`) usa por defecto argon2id con el perfil
RFC 9106 "low memory"; el hash guardado es el string PHC completo
(`$argon2id$v=19$m=...,t=...,p=...$<sal>$<hash>`), que incluye parametros y
sal. Lo usan la semilla del administrador y, despues, el modulo `users`.
"""

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()


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
    password: str, *, username: str | None = None, email: str | None = None
) -> list[str]:
    """Motivos (en espanol) por los que la contrasena es debil; [] si es fuerte.

    Fuerte = 12-128 caracteres, con minuscula, mayuscula, digito y simbolo.
    Decision del usuario (2026-10-22): se permite que contenga el usuario o la
    parte local del email; `username` y `email` se conservan en la firma por
    compatibilidad con los llamadores, pero ya no entran en la politica.
    """
    problems = []
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        problems.append(
            f"debe tener entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres"
        )
    if not any(c.islower() for c in password):
        problems.append("debe incluir una minúscula")
    if not any(c.isupper() for c in password):
        problems.append("debe incluir una mayúscula")
    if not any(c.isdigit() for c in password):
        problems.append("debe incluir un dígito")
    if all(c.isalnum() for c in password):
        problems.append("debe incluir un símbolo")
    return problems
