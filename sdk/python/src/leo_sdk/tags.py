"""Formato de los tags de accion `<app>.<modulo>.<verbo>` (kebab-case)."""

import re

TAG_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*){2}")


class InvalidTagError(ValueError):
    """Tag con formato invalido o de otra aplicacion."""


def validate_tag(tag: str, *, app_slug: str | None = None) -> str:
    """Devuelve `tag` si cumple el formato (y pertenece a `app_slug`, si se
    da); `InvalidTagError` si no."""
    if not isinstance(tag, str) or not TAG_PATTERN.fullmatch(tag):
        raise InvalidTagError(
            f"Tag de acción inválido: {tag!r}. Formato: <app>.<modulo>.<accion>, "
            "minúsculas y kebab-case por segmento."
        )
    if app_slug is not None and tag.split(".")[0] != app_slug:
        raise InvalidTagError(
            f"El tag {tag!r} no pertenece a la aplicación «{app_slug}»."
        )
    return tag
