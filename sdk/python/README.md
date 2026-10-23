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

## Llamar a otra app (credenciales de servicio)

Requisito: un admin de Leo concede a tu app un rol de la app destino (`/applications/{id}/service-access`). El `client_id`/`client_secret` son los de tu app.

```python
provider = ServiceTokenProvider(LeoClient(LeoSettings()))
http = httpx.AsyncClient(base_url="https://vladimir.example", auth=provider.auth("vladimir"))
await http.get("/things")  # Bearer automatico; ante 401 renueva el token y reintenta una vez
# o a mano: await provider.headers("vladimir") -> {"Authorization": "Bearer ..."}
```

El token se cachea en memoria hasta ~30 s antes de vencer (`margin_seconds`) con un solo canje concurrente por audiencia. Errores: `ServiceAccessDenied` (sin concesión), `InvalidTargetError` (audiencia inexistente), `TooManyAttemptsError` (`retry_after`), `InvalidClientError`, `LeoUnavailableError`.

## Editar el perfil o la contraseña de un usuario desde tu BFF

Requisito: un admin de Leo concede a tu app el rol de servicio `leo-self-service-delegate` (`leo.users.delegated-self-manage`). Solo sirve para usuarios sin permisos ni roles de Leo (p. ej. pacientes) y con el access token que Leo emitió a TU app.

```python
client = LeoClient(LeoSettings())
profile = await client.update_user_profile(user_access_token, first_name="Laura", email="n@x.com", current_password="...")
await client.change_user_password(user_access_token, current_password="...", new_password="...")
```

`current_password` es obligatoria para cambiar de correo y para cambiar la contraseña. Errores (`LeoError` con `code`): `invalid_token` (`InvalidTokenError`; `.is_user_token` si falla el token del usuario, no se reintenta), `forbidden`, `current_password_required`, `invalid_current_password`, `invalid_credentials`, `weak_password`, `same_password`, `duplicate`, `too_many_attempts` (`TooManyAttemptsError.retry_after`). Un 401 del token de servicio renueva el token y reintenta una vez.

## Aceptar llamadas de otras apps

`auth.current_user` y `auth.require_action(...)` aceptan además `Authorization: Bearer <token de servicio>` (sin cookie ni DPoP): el principal trae `principal_type == "service"`, `client_id` (la app llamadora), `permissions` y `session_id = None`. Un Bearer inválido da 401 `not_authenticated`; nunca cae a la cookie. Para endpoints solo de personas usa `Depends(auth.current_person)` (un servicio recibe 403 `user_required`); `/auth/me`, `/auth/activity` y `/auth/logout` ya lo exigen.

```python
@app.get("/things")
async def things(p: Annotated[LeoUser, auth.require_action("miapp.things.view")]):
    return {"caller": p.client_id if p.principal_type == "service" else p.username}
```

## Ajustes editables (`leo_sdk.settings_store`, extra opcional)

`pip install "leo-sdk[settings]"` (o `leo-sdk[settings] @ ../sdk/python` con uv). Requiere PostgreSQL y SQLAlchemy async. Pasos para una app:

1. Declarar las claves: `registry = SettingsRegistry([SettingDef("auth.max_x", "int", 5, "Descripción", min=1, max=20, unit="count", group="auth"), ...])`.
2. Modelos sobre su `Base`: `models = make_settings_models(Base, user_pk="users.id")` (importarlos en el registro de modelos de Alembic).
3. En una migración Alembic propia: `from leo_sdk.settings_store import migration` y `migration.upgrade(op)` / `migration.downgrade(op)` (crea las dos tablas y el trigger append-only).
   Apps sin tabla de usuarios: `make_settings_models(Base, user_pk=None)` y `migration.upgrade(op, users_table=None)` / `downgrade(op, users_table=None)`
   dejan `updated_by`/`changed_by` como UUID sin FK (mismo esquema, constraints, índice y triggers).
4. `store = SettingsStore(registry, session_factory, models)`; al arrancar `await store.sync_registry(initial_values)`; leer con `await store.get("auth.max_x")`.
5. Montar `build_settings_router(store, SettingsRouterDeps(view_dep=..., edit_dep=..., edit_security_dep=..., audit=...))` bajo el prefijo que quiera la app.

## Desarrollo

```
uv sync
uv run pytest -q          # unitarias + E2E contra la app real de Leo
uv run pytest tests/settings_store -q   # solo el módulo de ajustes (crea la BD leo_sdk_settings_test)
uv run ruff check .
uv run ruff format --check .
```

Los tests E2E (`tests/e2e/`) importan `backend/app` solo como dependencia de prueba y usan la
base `leo_test`; leen `DATABASE_URL` del entorno o de `backend/.env` (sin esa variable se omiten).

## Política de contraseñas

Endpoint público de Leo, sin credenciales (útil para validar antes de enviar):

```python
policy = await client.password_policy()  # PasswordPolicy; caché en memoria de 30 s
policy.check("abc")  # ["too_short", "no_uppercase", "no_digit", "no_symbol"]
policy.is_valid("Clave-Segura-2026!")  # True
```

Códigos: `too_short`, `too_long`, `no_lowercase`, `no_uppercase`, `no_digit`, `no_symbol`.
