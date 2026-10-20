"""Tipos/validadores Pydantic reusables. Los patrones vienen de
`app.core.db.checks` (misma fuente que los CHECK de la BD, no se duplican)."""

from typing import Annotated, Any, ClassVar
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.core.db.checks import ACTION_TAG_PATTERN, SLUG_PATTERN


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


Slug = Annotated[
    str,
    BeforeValidator(_strip),
    StringConstraints(min_length=1, max_length=64, pattern=SLUG_PATTERN),
    Field(
        description="Minúsculas, dígitos y guiones (kebab-case). No se puede "
        "cambiar después de creado.",
        examples=["mi-modulo"],
    ),
]

ActionTag = Annotated[
    str,
    BeforeValidator(_strip),
    StringConstraints(max_length=200, pattern=ACTION_TAG_PATTERN),
    Field(examples=["vladimir.samples.edit"]),
]


def text(max_length: int) -> type[str]:
    """Texto obligatorio, sin espacios en los extremos y no vacio."""
    return Annotated[  # type: ignore[return-value]
        str,
        BeforeValidator(_strip),
        StringConstraints(min_length=1, max_length=max_length),
    ]


def optional_text(max_length: int) -> type[str | None]:
    """Texto opcional; `null`, vacio o solo espacios se guarda como `None`."""

    def blank_to_none(value: object) -> object:
        value = _strip(value)
        return None if value == "" else value

    # La restriccion va dentro del `str` (no sobre la union): si no, un `null`
    # explicito reventaba con TypeError (500).
    return Annotated[  # type: ignore[return-value]
        Annotated[str, StringConstraints(max_length=max_length)] | None,
        BeforeValidator(blank_to_none),
    ]


def _http_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("Debe ser una URL absoluta http o https.")
    if parts.fragment or "#" in value:
        raise ValueError("No puede tener fragmento (#).")
    return value


HttpUrlStr = Annotated[
    str,
    BeforeValidator(_strip),
    StringConstraints(min_length=1, max_length=512),
    AfterValidator(_http_url),
]
"""URL http(s) absoluta sin fragmento, guardada tal cual (sin normalizar:
las `redirect_uris` se comparan por coincidencia exacta)."""


class UpdateModel(BaseModel):
    """Base de los `XUpdate` (PATCH): rechaza campos desconocidos y, con un
    mensaje claro, los inmutables (`immutable_fields`, p. ej. `slug`, `verb`:
    renombrarlos romperia los tags de accion ya usados en el codigo)."""

    model_config = ConfigDict(extra="forbid")
    immutable_fields: ClassVar[tuple[str, ...]] = ()
    non_nullable_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="before")
    @classmethod
    def _reject_immutable(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for name in cls.immutable_fields:
                if name in data:
                    raise ValueError(
                        f"El campo «{name}» no se puede cambiar una vez creado."
                    )
            for name in cls.non_nullable_fields:
                if name in data and data[name] is None:
                    raise ValueError(f"El campo «{name}» no puede quedar vacío.")
        return data
