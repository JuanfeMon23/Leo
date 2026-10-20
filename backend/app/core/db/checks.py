"""Formatos validados con CHECK en la BD, compartidos por varios modelos.

Las expresiones regulares tambien las importa el backend para validar antes
de llegar a la BD (misma fuente, no se duplican).
"""

from sqlalchemy import CheckConstraint

# Segmento kebab-case en minusculas: slug de app/modulo/rol y verbo de accion.
SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
# Tag de accion `<app>.<modulo>.<accion>` (regla transversal "Tags de accion").
ACTION_TAG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*){2}$"
# SHA-256 en hexadecimal minuscula (hash de token, code o client_secret).
SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"
# Thumbprint JWK SHA-256 (RFC 7638) o code_challenge S256: base64url sin
# relleno de 32 bytes = 43 caracteres.
B64URL_SHA256_PATTERN = r"^[A-Za-z0-9_-]{43}$"


def _sql(pattern: str) -> str:
    return pattern.replace("'", "''")


def slug_check(column: str = "slug") -> CheckConstraint:
    return CheckConstraint(
        f"{column} ~ '{_sql(SLUG_PATTERN)}'", name=f"{column}_format"
    )


def action_tag_check(column: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column} ~ '{_sql(ACTION_TAG_PATTERN)}'", name=f"{column}_format"
    )


def sha256_hex_check(column: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column} ~ '{_sql(SHA256_HEX_PATTERN)}'", name=f"{column}_format"
    )


def b64url_sha256_check(column: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column} ~ '{_sql(B64URL_SHA256_PATTERN)}'", name=f"{column}_format"
    )


def not_blank_check(column: str) -> CheckConstraint:
    return CheckConstraint(f"btrim({column}) <> ''", name=f"{column}_not_blank")
