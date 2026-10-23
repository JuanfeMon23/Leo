"""`client_ip`: X-Forwarded-For / X-Real-IP solo se creen si el par inmediato
es un proxy de confianza (`LEO_TRUSTED_PROXIES`); la falsificacion se ignora."""

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.core import client_ip as module
from app.core.client_ip import client_ip
from app.core.config import Settings, get_settings
from app.core.request_meta import request_meta


def make_request(
    peer: str | None, headers: dict[str, str] | list[tuple[str, str]] | None = None
) -> Request:
    items = headers.items() if isinstance(headers, dict) else (headers or [])
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(k.lower().encode(), v.encode()) for k, v in items],
            "client": (peer, 5000) if peer else None,
        }
    )


@pytest.fixture
def trust(monkeypatch):
    def set_trusted(value: str) -> None:
        settings = get_settings().model_copy(update={"leo_trusted_proxies": value})
        monkeypatch.setattr(module, "get_settings", lambda: settings)

    return set_trusted


def test_sin_proxies_de_confianza_se_ignoran_las_cabeceras(trust) -> None:
    trust("")
    request = make_request("203.0.113.9", {"X-Forwarded-For": "1.2.3.4"})
    assert client_ip(request) == "203.0.113.9"
    assert client_ip(make_request("203.0.113.9", {"X-Real-IP": "1.2.3.4"})) == (
        "203.0.113.9"
    )


def test_cliente_no_confiable_no_puede_falsificar_su_ip(trust) -> None:
    trust("10.0.0.0/8")
    request = make_request(
        "198.51.100.7", {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"}
    )
    assert client_ip(request) == "198.51.100.7"


def test_proxy_de_confianza_entrega_la_ip_del_cliente(trust) -> None:
    trust("10.0.0.0/8")
    request = make_request("10.1.2.3", {"X-Forwarded-For": "198.51.100.7"})
    assert client_ip(request) == "198.51.100.7"


def test_toma_el_primer_valor_no_confiable_de_derecha_a_izquierda(trust) -> None:
    trust("10.0.0.0/8, 192.168.0.1")
    # El cliente inyecto 1.1.1.1; el proxy de borde anadio 198.51.100.7.
    request = make_request(
        "10.0.0.5", {"X-Forwarded-For": "1.1.1.1, 198.51.100.7, 10.0.0.9, 192.168.0.1"}
    )
    assert client_ip(request) == "198.51.100.7"


def test_varias_cabeceras_xff_se_encadenan(trust) -> None:
    trust("10.0.0.0/8")
    request = make_request(
        "10.0.0.5",
        [("X-Forwarded-For", "1.1.1.1"), ("X-Forwarded-For", "198.51.100.7")],
    )
    assert client_ip(request) == "198.51.100.7"


def test_x_real_ip_solo_sin_xff_y_con_proxy_de_confianza(trust) -> None:
    trust("10.0.0.0/8")
    assert client_ip(make_request("10.0.0.5", {"X-Real-IP": "198.51.100.7"})) == (
        "198.51.100.7"
    )
    both = make_request(
        "10.0.0.5", {"X-Forwarded-For": "198.51.100.8", "X-Real-IP": "9.9.9.9"}
    )
    assert client_ip(both) == "198.51.100.8"


def test_valor_ilegible_cae_a_la_ip_del_proxy(trust) -> None:
    trust("10.0.0.0/8")
    request = make_request("10.0.0.5", {"X-Forwarded-For": "198.51.100.7, basura"})
    assert client_ip(request) == "10.0.0.5"


def test_toda_la_cadena_de_confianza_devuelve_el_primero(trust) -> None:
    trust("10.0.0.0/8")
    request = make_request("10.0.0.5", {"X-Forwarded-For": "10.0.0.1, 10.0.0.2"})
    assert client_ip(request) == "10.0.0.1"


def test_ipv6_y_normalizacion(trust) -> None:
    trust("fd00::/8")
    request = make_request("fd00::1", {"X-Forwarded-For": "2001:DB8:0::7"})
    assert client_ip(request) == "2001:db8::7"


def test_sin_peer_no_hay_ip(trust) -> None:
    trust("10.0.0.0/8")
    assert client_ip(make_request(None, {"X-Forwarded-For": "1.2.3.4"})) is None


def test_request_meta_usa_client_ip(trust) -> None:
    trust("10.0.0.0/8")
    request = make_request("10.0.0.5", {"X-Forwarded-For": "198.51.100.7"})
    assert request_meta(request).ip == "198.51.100.7"
    forged = make_request("198.51.100.9", {"X-Forwarded-For": "1.2.3.4"})
    assert request_meta(forged).ip == "198.51.100.9"


def test_trusted_proxies_invalido_falla_al_arrancar() -> None:
    base = get_settings().model_dump()
    with pytest.raises(ValidationError):
        Settings(**{**base, "leo_trusted_proxies": "10.0.0.0/8, no-es-ip"})
