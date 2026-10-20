"""Reloj de la aplicacion (UTC, con zona).

Todo lo que compara tiempos en Python (inactividad, expiraciones, bloqueo,
`iat` de DPoP) llama a `clock.now()` en vez de `datetime.now()`, para que
los tests puedan adelantar el reloj (`monkeypatch.setattr(clock, "now", ...)`).
Usar siempre `from app.core import clock` + `clock.now()` (no importar la
funcion suelta: el monkeypatch no la alcanzaria).
"""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
