# leo_sdk

Paquete Python para que el backend FastAPI de una app se integre con Leo (SSO, permisos y auditoría).

## Requisitos

- Python 3.13 y [uv](https://docs.astral.sh/uv/).
- La app registrada en Leo (su `client_id` es su slug) con su `client_secret` y su `redirect_uri`.
- Variables de entorno (o `.env`); el secreto solo por entorno:

| Variable | Qué es |
|---|---|
| `LEO_URL` | Origen del frontend de Leo (pantalla `/authorize`) |
| `LEO_API_URL` | API de Leo con `/api/v1` (ej. `http://localhost:8100/api/v1`) |
| `APP_CLIENT_ID` / `APP_CLIENT_SECRET` | Credenciales de la app en Leo |
| `PUBLIC_URL` | URL pública de este backend (esquema + host + puerto); fija el `htu` de DPoP |
| `APP_REDIRECT_URI` | Opcional. `redirect_uri` registrada (por defecto `PUBLIC_URL/auth/callback`) |
| `APP_STATE_SECRET` | Opcional. Clave de la cookie de flujo (por defecto se deriva del secreto) |

Otras opciones de `LeoSettings` (nombres de cookie, `cookie_secure`, `introspection_ttl_seconds`, `flow_ttl_seconds`, `http_timeout_seconds`) se pasan por entorno o por código.

## Usar

```python
auth = LeoAuth(LeoSettings(), catalog=catalog)
app.include_router(leo_router(auth))  # /auth/login /callback /me /activity /logout
auth.install(app)  # handler de errores y cookies


@app.get("/things")
async def things(
    user: Annotated[LeoUser, auth.require_action("miapp.things.view")],
): ...
```

Ejemplo completo y ejecutable: `examples/minimal_app.py`
(`uv run uvicorn examples.minimal_app:app --port 8200`).

Cada petición del navegador al backend lleva la cookie de sesión y el header `DPoP`
(lo agrega `leo-client`). `GET /auth/login` y `GET /auth/callback` también lo requieren:
el cliente llama a `/auth/login`, navega a la `authorize_url` devuelta y, al volver,
llama a `/auth/callback?code=...&state=...`.

`GET /auth/me` y `GET /auth/callback` responden `{user, session, applications}`:
`user` (`id, username, name, first_name, last_name, email, permissions, session_id`),
`session` (`expires_at, last_activity_at, idle_timeout_seconds`) y `applications`
(`[{slug, name, base_url}]`). Si Leo aún no envía nombre/apellido, apps o `last_activity_at`
en la introspección, el SDK usa `first_name = name`, `last_name = ""`, `applications = []` y la
hora de la última introspección; cuando Leo los envía, los usa solo.

## Desarrollo

```
uv sync
uv run pytest -q          # unitarias + E2E contra la app real de Leo
uv run ruff check .
uv run ruff format --check .
```

Los tests E2E (`tests/e2e/`) importan `backend/app` solo como dependencia de prueba y usan la
base `leo_test`; leen `DATABASE_URL` del entorno o de `backend/.env` (sin esa variable se omiten).
