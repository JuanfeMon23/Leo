"""Contrato de permisos de Leo para el frontend.

Construye `frontend/app/generated/permissions.json` desde el catalogo en codigo
(sin tocar la BD). `uv run python -m app.core.permissions_export` lo escribe;
con `--check` sale con codigo 1 si el archivo commiteado difiere.
"""

import json
import sys
from pathlib import Path

from app.core.db.seeds.catalog import (
    LEO_ACTION_NAMES,
    LEO_APP_SLUG,
    LEO_MODULES,
    derived_action_name,
)

CONTRACT_PATH = (
    Path(__file__).resolve().parents[3] / "frontend/app/generated/permissions.json"
)
EVENT_PREFIX = "Evento:"
MISALIGNED_MESSAGE = (
    "tags desalineados: ejecuta uv run python -m app.core.permissions_export"
)


def build_contract() -> dict:
    modules = []
    for module_slug, (module_name, verbs) in LEO_MODULES.items():
        actions = []
        for verb, description in verbs.items():
            tag = f"{LEO_APP_SLUG}.{module_slug}.{verb}"
            name = LEO_ACTION_NAMES.get(tag, derived_action_name(verb))
            actions.append(
                {
                    "tag": tag,
                    "verb": verb,
                    "name": name,
                    "description": description,
                    "assignable": not name.startswith(EVENT_PREFIX),
                }
            )
        modules.append(
            {
                "slug": module_slug,
                "name": module_name,
                "description": "",
                "actions": actions,
            }
        )
    return {"app": LEO_APP_SLUG, "modules": modules}


def render_contract() -> str:
    return json.dumps(build_contract(), ensure_ascii=False, indent=2) + "\n"


def is_aligned(path: Path | None = None) -> bool:
    path = path or CONTRACT_PATH
    return path.is_file() and path.read_bytes() == render_contract().encode("utf-8")


def main(argv: list[str]) -> int:
    if "--check" in argv:
        if is_aligned():
            return 0
        print(MISALIGNED_MESSAGE)
        return 1
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT_PATH.write_bytes(render_contract().encode("utf-8"))
    print(f"escrito {CONTRACT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
