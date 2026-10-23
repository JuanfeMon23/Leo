"""`GET /auth/password-policy`: publica (sin sesion), refleja los ajustes
vigentes sin reiniciar y esta limitada por IP."""

from app.testkit import set_setting

URL = "/api/v1/auth/password-policy"
DEFAULT = {
    "min_length": 12,
    "max_length": 128,
    "require_lowercase": True,
    "require_uppercase": True,
    "require_digit": True,
    "require_symbol": True,
}


async def test_publica_sin_sesion_con_cache_corto(session, client):
    await session.commit()
    response = await client.get(URL)
    assert response.status_code == 200, response.text
    assert response.json() == DEFAULT
    assert response.headers["cache-control"] == "public, max-age=30"
    assert "set-cookie" not in response.headers


async def test_cambia_al_editar_el_ajuste_sin_reiniciar(session, client):
    await session.commit()
    assert (await client.get(URL)).json() == DEFAULT
    await set_setting(session, "password.min_length", 20)
    await set_setting(session, "password.require_symbol", False)
    await session.commit()
    body = (await client.get(URL)).json()
    assert body == {**DEFAULT, "min_length": 20, "require_symbol": False}


async def test_limite_por_ip(session, client):
    await set_setting(session, "rate_limit.public_policy_per_window", 10)
    await session.commit()
    for _ in range(10):
        assert (await client.get(URL)).status_code == 200
    response = await client.get(URL)
    assert response.status_code == 429
    assert response.json()["code"] == "too_many_attempts"
    assert int(response.headers["retry-after"]) >= 1
