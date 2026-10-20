"""Helpers de tests compartidos por el nucleo y todos los modulos (fabricas
de datos, "navegador" con llave DPoP, credenciales de cliente). No es codigo
de produccion: solo lo importan los tests y `app/conftest.py`.
"""

import base64
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import new_opaque_token, sha256_b64url
from app.core.db.seeds.catalog import (
    LEO_ADMIN_ROLE_SLUG,
    LEO_APP_SLUG,
    derived_action_name,
)
from app.core.security.passwords import hash_password
from app.core.tests.dpop_keys import DpopKey
from app.modules.applications.models import Action, Application, AppModule
from app.modules.roles.models import Role, RoleAction, ServiceGrant
from app.modules.users.models import User, UserRole

PUBLIC_URL = "https://leo.test"
FRONTEND_URL = "https://admin.leo.test"
STRONG_PASSWORD = "Clave-Segura-2026!"
COOKIE = "__Host-leo_session"


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


_HASH_CACHE: dict[str, str] = {}


def _hash(password: str) -> str:
    # argon2 es lento a proposito; en tests se reutiliza el hash por clave.
    if password not in _HASH_CACHE:
        _HASH_CACHE[password] = hash_password(password)
    return _HASH_CACHE[password]


async def make_user(
    session: AsyncSession, *, password: str = STRONG_PASSWORD, **overrides: Any
) -> User:
    username = overrides.pop("username", None) or unique("user")
    user = User(
        username=username,
        email=overrides.pop("email", f"{username}@example.com"),
        password_hash=_hash(password),
        document_type=overrides.pop("document_type", "CC"),
        document_number=overrides.pop("document_number", uuid4().hex[:16].upper()),
        first_name=overrides.pop("first_name", "Ana"),
        last_name=overrides.pop("last_name", "Gómez"),
        **overrides,
    )
    session.add(user)
    await session.flush()
    return user


async def leo_app(session: AsyncSession) -> Application:
    return (
        await session.scalars(
            select(Application).where(Application.slug == LEO_APP_SLUG)
        )
    ).one()


async def leo_admin_role(session: AsyncSession) -> Role:
    app = await leo_app(session)
    return (
        await session.scalars(
            select(Role).where(
                Role.application_id == app.id, Role.slug == LEO_ADMIN_ROLE_SLUG
            )
        )
    ).one()


async def grant(session: AsyncSession, user: User, role: Role) -> None:
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()


class ClientCredentials:
    """App cliente de prueba con su secreto en claro (solo en tests)."""

    def __init__(self, app: Application, secret: str) -> None:
        self.app = app
        self.secret = secret

    @property
    def client_id(self) -> str:
        return self.app.client_id

    def basic(self, secret: str | None = None) -> dict[str, str]:
        raw = f"{self.client_id}:{secret or self.secret}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


async def make_client_app(
    session: AsyncSession,
    *,
    slug: str | None = None,
    redirect_uris: list[str] | None = None,
    tags: list[str] | None = None,
) -> ClientCredentials:
    """App con client_secret conocido y, si se piden, acciones `<slug>.<mod>.<verbo>`
    (`tags` como `"mod.verbo"`)."""
    slug = slug or unique("app")
    secret = new_opaque_token()
    app = Application(
        slug=slug,
        name=f"App {slug}",
        base_url=f"https://{slug}.test",
        redirect_uris=redirect_uris or [f"https://{slug}.test/callback"],
        client_id=slug,
        client_secret_hash=secret.hash,
    )
    session.add(app)
    await session.flush()
    for tag in tags or []:
        await make_action(session, app, tag)
    return ClientCredentials(app, secret.value)


async def make_action(
    session: AsyncSession, app: Application, tag: str, name: str | None = None
) -> Action:
    module_slug, verb = tag.split(".")
    module = await session.scalar(
        select(AppModule).where(
            AppModule.application_id == app.id, AppModule.slug == module_slug
        )
    )
    if module is None:
        module = AppModule(application_id=app.id, slug=module_slug, name=module_slug)
        session.add(module)
        await session.flush()
    action = Action(
        application_id=app.id,
        module_id=module.id,
        verb=verb,
        tag=f"{app.slug}.{module_slug}.{verb}",
        name=name or derived_action_name(verb),
    )
    session.add(action)
    await session.flush()
    return action


async def make_role(
    session: AsyncSession, app_id: UUID, tags: list[str] | None = None, **fields: Any
) -> Role:
    role = Role(
        application_id=app_id,
        slug=fields.pop("slug", None) or unique("role"),
        name=fields.pop("name", "Rol de prueba"),
        **fields,
    )
    session.add(role)
    await session.flush()
    if tags:
        actions = await session.scalars(select(Action).where(Action.tag.in_(tags)))
        found = list(actions)
        assert len(found) == len(tags), f"tags inexistentes: {tags}"
        for action in found:
            session.add(
                RoleAction(role_id=role.id, action_id=action.id, application_id=app_id)
            )
        await session.flush()
    return role


async def grant_service_access(
    session: AsyncSession, caller: Application, role: Role
) -> ServiceGrant:
    """Concede a la app llamadora `caller` un rol de OTRA app (service_grants)."""
    service_grant = ServiceGrant(
        caller_application_id=caller.id,
        role_id=role.id,
        application_id=role.application_id,
    )
    session.add(service_grant)
    await session.flush()
    return service_grant


def pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge S256)."""
    verifier = new_opaque_token().value + "-verifier"
    return verifier, sha256_b64url(verifier)


class Browser:
    """Navegador de prueba: cliente HTTP con cookie jar + llave DPoP propia.
    Cada peticion lleva una prueba DPoP nueva para `PUBLIC_URL + path`."""

    def __init__(self, client: AsyncClient, key: DpopKey | None = None) -> None:
        self.client = client
        self.key = key or DpopKey()

    def proof(self, method: str, path: str) -> str:
        return self.key.proof(method.upper(), PUBLIC_URL + path.split("?")[0])

    async def request(
        self, method: str, path: str, *, dpop: bool = True, **kwargs: Any
    ) -> Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if dpop:
            headers.setdefault("DPoP", self.proof(method, path))
        return await self.client.request(method, path, headers=headers, **kwargs)

    async def get(self, path: str, **kwargs: Any) -> Response:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Response:
        return await self.request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> Response:
        return await self.request("PATCH", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> Response:
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Response:
        return await self.request("DELETE", path, **kwargs)

    async def login(self, login: str, password: str = STRONG_PASSWORD) -> Response:
        return await self.post(
            "/api/v1/auth/login", json={"login": login, "password": password}
        )
