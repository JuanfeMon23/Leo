"""Fixtures compartidas por los tests de la API (nucleo y modulos).

Todo corre contra la BD `leo_test` (la deja en `alembic upgrade head` la
fixture `migrated` de `app/core/db/tests/conftest.py`), nunca contra la de
desarrollo. Configuracion de prueba con valores obviamente falsos.

- `session`: transaccion externa que se revierte al terminar el test (los
  `commit()` de los controllers son savepoints); con la semilla de la app
  `leo` (modulos, acciones `leo.*` y rol `leo-admin`) ya aplicada.
- `client`: httpx sobre la app ASGI con `get_session` -> `session`.
- `make_browser()`: "navegadores" independientes (cookie jar + llave DPoP
  propios); `browser` es uno; `admin` ya inicio sesion con un usuario que
  tiene `leo-admin`. `login_as(session, make_browser, user)` para otros.
- `client`: cliente HTTP sin llave (backends con client credentials).
"""

import os

TEST_ENV = {
    "LEO_FRONTEND_URL": "https://admin.leo.test",
    "LEO_PUBLIC_URL": "https://leo.test",
    "LEO_IDLE_TIMEOUT_MINUTES": "30",
    "LEO_ACCESS_TOKEN_MINUTES": "15",
    "LEO_SESSION_MAX_HOURS": "12",
    "LEO_COOKIE_SECURE": "true",
    "LEO_LOGIN_MAX_FAILED_ATTEMPTS": "5",
    "LEO_LOGIN_LOCK_MINUTES": "15",
    "LEO_LOGIN_RATE_LIMIT_PER_MINUTE": "20",
}
os.environ.update(TEST_ENV)

from collections.abc import AsyncGenerator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.db.tests.conftest import TEST_URL, migrated  # noqa: F401

# Desde aqui toda la app usa `leo_test`.
os.environ["DATABASE_URL"] = TEST_URL
get_settings.cache_clear()

from app.core.database import get_session
from app.core.db.seeds.leo_app import (
    seed_leo_admin_role,
    seed_leo_application,
)
from app.core.dpop import replay_cache
from app.main import app
from app.modules.auth import login_limiters, service_token_limiter
from app.modules.users.models import User
from app.testkit import (
    FRONTEND_URL,
    PUBLIC_URL,
    Browser,
    grant,
    leo_admin_role,
    make_user,
)


@pytest_asyncio.fixture(scope="session")
async def api_engine(migrated: None) -> AsyncGenerator[AsyncEngine]:  # noqa: F811
    engine = create_async_engine(TEST_URL, poolclass=pool.NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(api_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    async with api_engine.connect() as connection:
        outer = await connection.begin()
        await connection.run_sync(
            lambda sync: seed_leo_admin_role(
                sync, seed_leo_application(sync, FRONTEND_URL)
            )
        )
        maker = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with maker() as test_session:
            yield test_session
        await outer.rollback()


@pytest.fixture(autouse=True)
def _reset_process_state() -> None:
    """Limitadores del login y cache anti-replay son de proceso: cada test
    empieza limpio."""
    login_limiters().reset()
    service_token_limiter().reset()
    replay_cache.clear()


@pytest_asyncio.fixture
async def make_browser(session: AsyncSession) -> AsyncGenerator[Callable[[], Browser]]:
    """Fabrica de navegadores independientes (cookie jar y llave DPoP
    propios) sobre la misma sesion de BD del test."""

    async def override() -> AsyncGenerator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override
    clients: list[AsyncClient] = []

    def factory() -> Browser:
        http = AsyncClient(transport=ASGITransport(app=app), base_url=PUBLIC_URL)
        clients.append(http)
        return Browser(http)

    yield factory
    for http in clients:
        await http.aclose()
    app.dependency_overrides.clear()


@pytest.fixture
def client(make_browser: Callable[[], Browser]) -> AsyncClient:
    """Cliente HTTP sin llave (backends de apps con client credentials)."""
    return make_browser().client


@pytest.fixture
def browser(make_browser: Callable[[], Browser]) -> Browser:
    return make_browser()


async def login_as(
    session: AsyncSession, make_browser: Callable[[], Browser], user: User
) -> Browser:
    await session.commit()
    nav = make_browser()
    response = await nav.login(user.username)
    assert response.status_code == 200, response.text
    nav.user = user  # type: ignore[attr-defined]
    return nav


@pytest_asyncio.fixture
async def admin(session: AsyncSession, make_browser: Callable[[], Browser]) -> Browser:
    """Navegador con sesion de un usuario `leo-admin` (todas las `leo.*`)."""
    user = await make_user(session)
    await grant(session, user, await leo_admin_role(session))
    return await login_as(session, make_browser, user)
