"""Catalogo de modulos y acciones que la app declara y publica en Leo.

    catalog = Catalog("vladimir")
    catalog.module("samples", "Muestras")
    catalog.action("samples", "edit", "Editar muestras")

`LeoAuth.sync_catalog()` lo publica en `PUT /applications/{slug}/catalog` y
`LeoAuth.check_catalog()` compara los tags usados por `require_action` con lo
declarado: un tag usado y no declarado no existe en Leo y nadie podria tenerlo.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from leo_sdk.tags import validate_tag

MAX_NAME = 120


class CatalogMismatchError(Exception):
    """Hay tags usados en el codigo que no estan declarados en el catalogo."""

    def __init__(self, missing: Iterable[str]) -> None:
        self.missing = sorted(missing)
        super().__init__(
            "Tags usados por require_action y no declarados en el catálogo: "
            + ", ".join(self.missing)
        )


@dataclass(frozen=True)
class ActionDecl:
    module: str
    verb: str
    name: str
    description: str | None = None


@dataclass(frozen=True)
class ModuleDecl:
    slug: str
    name: str
    description: str | None = None


def _clean_name(name: str, what: str) -> str:
    name = name.strip() if isinstance(name, str) else ""
    if not name or len(name) > MAX_NAME:
        raise ValueError(
            f"El nombre de {what} debe tener entre 1 y {MAX_NAME} caracteres."
        )
    return name


class Catalog:
    def __init__(self, app_slug: str) -> None:
        self.app_slug = app_slug
        self._modules: dict[str, ModuleDecl] = {}
        self._actions: dict[str, ActionDecl] = {}  # tag -> declaracion

    def module(self, slug: str, name: str, description: str | None = None) -> "Catalog":
        validate_tag(f"{self.app_slug}.{slug}.x")
        if slug in self._modules:
            raise ValueError(f"Módulo repetido en el catálogo: {slug}")
        self._modules[slug] = ModuleDecl(slug, _clean_name(name, "módulo"), description)
        return self

    def action(
        self, module: str, verb: str, name: str, description: str | None = None
    ) -> Callable[[Any], Any]:
        """Declara una accion. Devuelve ademas un decorador neutro (devuelve la
        funcion intacta) para declararla junto a la ruta que protege."""
        if module not in self._modules:
            raise ValueError(f"Declara primero el módulo «{module}».")
        tag = validate_tag(f"{self.app_slug}.{module}.{verb}", app_slug=self.app_slug)
        if tag in self._actions:
            raise ValueError(f"Acción repetida en el catálogo: {tag}")
        self._actions[tag] = ActionDecl(
            module, verb, _clean_name(name, "acción"), description
        )

        def decorator(fn: Any) -> Any:
            return fn

        return decorator

    @property
    def tags(self) -> frozenset[str]:
        return frozenset(self._actions)

    def undeclared(self, used: Iterable[str]) -> list[str]:
        return sorted(set(used) - self.tags)

    def to_payload(self, *, deactivate_missing: bool = False) -> dict[str, Any]:
        """Cuerpo de `PUT /applications/{slug}/catalog`. Los campos opcionales
        vacios se omiten (Leo no acepta `null` explicito en `description`)."""

        def clean(**fields: Any) -> dict[str, Any]:
            return {k: v for k, v in fields.items() if v is not None}

        modules = []
        for module in self._modules.values():
            actions = [
                clean(verb=a.verb, name=a.name, description=a.description)
                for a in self._actions.values()
                if a.module == module.slug
            ]
            modules.append(
                clean(
                    slug=module.slug,
                    name=module.name,
                    description=module.description,
                    actions=actions,
                )
            )
        return {"modules": modules, "deactivate_missing": deactivate_missing}
