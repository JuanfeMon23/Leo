"""Nucleo: tokens opacos, diff de auditoria, limitador, errores uniformes
(validacion, BD por SQLSTATE, 500) y CORS."""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core import clock
from app.core.audit import diff, is_sensitive
from app.core.crypto import (
    b64url_decode,
    constant_time_equals,
    new_opaque_token,
    pkce_s256_matches,
    sha256_b64url,
    sha256_hex,
)
from app.core.database import SessionDep, get_session
from app.core.exceptions import register_exception_handlers
from app.core.rate_limit import SlidingWindowLimiter

# --- authz ---


@pytest.mark.parametrize(
    "tag",
    [
        "leo.auth.login",
        "leo.auth.logout",
        "leo.auth.lock",
        "leo.auth.idle-timeout",
        "leo.auth.refresh-reuse",
        "leo.auth.token",
        "leo.auth.authorize",
        "leo.applications.sync-catalog",
    ],
)
def test_require_action_rechaza_tags_de_evento(tag: str) -> None:
    """Un tag de evento (descripcion "Evento:") solo se audita; si protegiera
    un endpoint, darselo a un rol abriria esa ruta sin querer."""
    from app.core.authz import require_action, require_actor

    with pytest.raises(ValueError, match="evento"):
        require_action(tag)
    with pytest.raises(ValueError, match="evento"):
        require_actor(tag)


def test_require_action_rechaza_tags_no_registrados() -> None:
    from app.core.authz import require_action

    with pytest.raises(ValueError, match="registrad"):
        require_action("leo.users.no-existe")


def test_require_action_acepta_permisos_registrados() -> None:
    from app.core.authz import require_action

    assert require_action("leo.users.view") is not None


# --- crypto ---


def test_token_opaco_256_bits_y_solo_hash_a_la_bd() -> None:
    token = new_opaque_token()
    assert len(b64url_decode(token.value)) == 32
    assert token.hash == sha256_hex(token.value) and len(token.hash) == 64
    assert new_opaque_token().value != token.value


def test_pkce_s256_vector_rfc7636() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert sha256_b64url(verifier) == challenge
    assert pkce_s256_matches(verifier, challenge)
    assert not pkce_s256_matches(verifier + "x", challenge)


def test_comparacion_en_tiempo_constante() -> None:
    assert constant_time_equals("abc", "abc")
    assert not constant_time_equals("abc", "abd")


def test_b64url_rechaza_relleno_y_basura() -> None:
    for bad in ("YQ==", "a$b", "Y"):
        with pytest.raises(ValueError):
            b64url_decode(bad)


# --- diff de auditoria ---


def test_diff_solo_campos_cambiados_y_sin_sensibles() -> None:
    before = {"name": "A", "slug": "a", "password_hash": "x", "client_secret": "s"}
    after = {"name": "B", "slug": "a", "password_hash": "y", "client_secret": "t"}
    assert diff(before, after) == {"name": {"before": "A", "after": "B"}}
    assert diff(before, before) is None
    assert diff(None, {"slug": "a"}) == {"slug": {"before": None, "after": "a"}}


@pytest.mark.parametrize(
    "name", ["password", "token_hash", "client_secret_hash", "refresh_token", "jkt"]
)
def test_campos_sensibles(name: str) -> None:
    assert is_sensitive(name)


# --- limitador ---


async def test_limitador_ventana_deslizante() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    now = clock.now()
    await limiter.hit("k", now)
    assert await limiter.retry_after("k", now) == 0
    await limiter.hit("k", now)
    assert 0 < await limiter.retry_after("k", now) <= 61
    assert await limiter.retry_after("k", now + timedelta(seconds=61)) == 0
    assert await limiter.retry_after("otra", now) == 0


# --- errores uniformes ---


class Body(BaseModel):
    nombre: str = Field(min_length=3)
    edad: int


@pytest.fixture
async def errors_client(session):
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/body")
    async def body(data: Body) -> dict:
        return {}

    @app.post("/sql")
    async def sql(session: SessionDep, statement: str) -> dict:
        await session.execute(text(statement))
        return {}

    @app.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("detalle interno que no debe filtrarse")

    async def override():
        yield session

    app.dependency_overrides[get_session] = override
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as http:
        yield http


async def test_validacion_422_en_espanol(errors_client) -> None:
    response = await errors_client.post("/body", json={"nombre": "ab"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert {
        "field": "nombre",
        "message": "Es demasiado corto (mínimo 3 caracteres).",
    } in body["details"]
    assert {"field": "edad", "message": "Este campo es obligatorio."} in body["details"]


@pytest.mark.parametrize(
    ("statement", "status", "code"),
    [
        (
            (
                "INSERT INTO applications (slug, name, base_url, client_id, client_secret_hash) "
                "SELECT slug, name, base_url, client_id || '-x', client_secret_hash "
                "FROM applications WHERE slug = 'leo'"
            ),
            409,
            "duplicate",
        ),
        (
            (
                "INSERT INTO app_modules (application_id, slug, name) "
                "VALUES ('00000000-0000-0000-0000-000000000000', 'm', 'M')"
            ),
            422,
            "invalid_reference",
        ),
        (
            "UPDATE applications SET slug = 'Mal Slug' WHERE slug = 'leo'",
            422,
            "validation_error",
        ),
        ("TRUNCATE audit_events", 409, "append_only"),
    ],
)
async def test_errores_de_bd_por_sqlstate(
    errors_client, statement, status, code
) -> None:
    response = await errors_client.post("/sql", params={"statement": statement})
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


async def test_error_inesperado_500_sin_detalles(errors_client) -> None:
    response = await errors_client.get("/boom")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "detalle interno" not in response.text


# --- CORS ---


async def test_cors_solo_el_frontend_de_leo_con_credenciales(client) -> None:
    allowed = await client.options(
        "/api/v1/auth/me",
        headers={
            "Origin": "https://admin.leo.test",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "DPoP",
        },
    )
    assert allowed.headers["access-control-allow-origin"] == "https://admin.leo.test"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    other = await client.options(
        "/api/v1/auth/me",
        headers={"Origin": "https://evil.test", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in other.headers
