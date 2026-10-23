"""IP real del cliente detras de un proxy inverso: unica fuente de verdad.

`client_ip(request)` es la UNICA forma de obtener la IP para limites de
intentos, sesiones y auditoria (nada lee `request.client.host` directo).

`X-Forwarded-For` / `X-Real-IP` los escribe cualquiera: solo se les cree si
el par inmediato de la conexion (`request.client.host`) esta en
`LEO_TRUSTED_PROXIES` (IP/CIDR separados por comas; vacio = nunca). Entonces
se recorre `X-Forwarded-For` de derecha a izquierda y se toma el primer
valor que NO sea un proxy de confianza (lo que un cliente inyecte queda a la
izquierda del que anadio el proxy y se ignora). Si no hay `X-Forwarded-For`,
se usa `X-Real-IP`. Un valor ilegible cae a la IP del par (fail-closed: todos
los clientes de ese proxy comparten limite en vez de burlarlo).

Al desplegar detras de proxy, uvicorn debe arrancar con `--no-proxy-headers`
para que no reescriba el peer por su cuenta.
"""

import ipaddress
from functools import lru_cache

from fastapi import Request

from app.core.config import get_settings

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache
def parse_trusted_proxies(value: str) -> tuple[IPNetwork, ...]:
    return tuple(
        ipaddress.ip_network(item.strip(), strict=False)
        for item in value.split(",")
        if item.strip()
    )


def _parse(value: str | None) -> IPAddress | None:
    try:
        return ipaddress.ip_address(value.strip()) if value else None
    except ValueError:
        return None


def _is_trusted(ip: IPAddress, networks: tuple[IPNetwork, ...]) -> bool:
    return any(ip.version == net.version and ip in net for net in networks)


def client_ip(request: Request) -> str | None:
    """IP del cliente como texto normalizado, o `None` si no se conoce."""
    peer = _parse(request.client.host if request.client else None)
    if peer is None:
        return None
    networks = parse_trusted_proxies(get_settings().leo_trusted_proxies)
    if not networks or not _is_trusted(peer, networks):
        return str(peer)

    forwarded = [
        part
        for header in request.headers.getlist("x-forwarded-for")
        for part in header.split(",")
    ]
    if not forwarded:
        real = _parse(request.headers.get("x-real-ip"))
        return str(real if real is not None else peer)
    for part in reversed(forwarded):
        ip = _parse(part)
        if ip is None:
            return str(peer)
        if not _is_trusted(ip, networks):
            return str(ip)
    return str(_parse(forwarded[0]) or peer)  # toda la cadena es de confianza
