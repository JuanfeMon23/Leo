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
