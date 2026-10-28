# Leo

## Requisitos

Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js con [pnpm](https://pnpm.io/) y PostgreSQL 18.

## Ejecutar

1. Crea una base de datos vacía (por ejemplo `leo`).
2. Variables de entorno:
   ```bash
   cp backend/.env.example backend/.env      # DATABASE_URL, CORS_ORIGINS, LEO_ADMIN_*
   cp frontend/.env.example frontend/.env    # NUXT_PUBLIC_API_BASE
   ```
3. Backend (`http://localhost:8100`, documentación en `/docs`):
   ```bash
   cd backend
   uv sync
   uv run alembic upgrade head
   uv run python -m app.core.db.seeds
   uv run uvicorn app.main:app --port 8100 --reload
   ```
4. Frontend (`http://localhost:3100`):
   ```bash
   cd frontend
   pnpm install
   pnpm run dev
   ```

## Tags de acciones (contrato backend ↔ frontend)

El catálogo vive en el backend; el frontend lee `frontend/app/generated/permissions.json` (generado y commiteado). Al cambiar tags en `backend/app/core/db/seeds/catalog.py`, regenéralo y commitéalo:

```bash
cd backend
uv run python -m app.core.permissions_export          # escribe el JSON
uv run python -m app.core.permissions_export --check  # sale con 1 si está desalineado
```

Un test de backend y otro de frontend fallan si el JSON no coincide con el catálogo o si el frontend usa un tag inexistente.

## Ajustes (backend)

Las políticas (inactividad, vida de tokens y sesión, bloqueo de login, límites de intentos, contraseñas, paginación, export) ya NO son variables de entorno: se editan en la pantalla Ajustes (tabla `settings`, migración 0008). Ya no se usan `LEO_IDLE_TIMEOUT_MINUTES`, `LEO_ACCESS_TOKEN_MINUTES`, `LEO_SESSION_MAX_HOURS`, `LEO_LOGIN_*`, `LEO_SERVICE_TOKEN_*`, `LEO_PROVISION_*` ni `LEO_DELEGATED_*`; si siguen definidas, solo se leen en el primer arranque como valor inicial de la clave que aún no existe. El backend depende de `sdk/python` por ruta local (`uv sync` en `backend/`).

## Producción (backend)

Endurecimientos opcionales por variable de entorno (ver `backend/.env.example`); los valores por defecto sirven para desarrollo.

- **Límites de intentos compartidos entre procesos:** `LEO_RATE_LIMIT_BACKEND=postgres` (por defecto `memory`, que cuenta por proceso y no sirve con varias instancias). Usa la tabla `rate_limit_hits` (migración 0006); no requiere Redis.
- **IP real detrás de un proxy:** `LEO_TRUSTED_PROXIES=10.0.0.0/8,192.168.1.5` (IP/CIDR del proxy inverso; vacío = se ignoran `X-Forwarded-For`/`X-Real-IP`). Arranca uvicorn con `--no-proxy-headers`.
- **Roles de BD de mínimo privilegio** (`leo_migrator` para Alembic, `leo_app` para la API). Requiere un superusuario de PostgreSQL:
  ```bash
  cd backend
  psql -d leo -v ON_ERROR_STOP=1 -f deploy/db_roles.sql   # crea los roles (sin contraseña)
  psql -d leo -c "\password leo_migrator"                 # fija las contraseñas
  psql -d leo -c "\password leo_app"
  # .env: MIGRATION_DATABASE_URL con leo_migrator, DATABASE_URL con leo_app
  uv run alembic upgrade head                             # corre como leo_migrator
  psql -d leo -v ON_ERROR_STOP=1 -f deploy/db_roles.sql   # re-aplicar tras cada migración que agregue tablas
  ```
  La semilla inicial (`python -m app.core.db.seeds`) también puede correr con `leo_app`.
