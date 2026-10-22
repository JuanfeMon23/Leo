"""Crea la app FastAPI de Leo y registra los routers de los modulos."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.authz import configure_authz
from app.core.client_auth import configure_client_auth
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.request_meta import REQUEST_ID_HEADER, RequestIdMiddleware
from app.core.service_authz import configure_service_authz
from app.modules import applications, audit, auth, roles, users

API = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Leo API",
        version="0.1.0",
        description="SSO, control de acceso y auditoría central del ecosistema.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.leo_frontend_url.rstrip("/")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "DPoP", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER, "WWW-Authenticate", "Retry-After"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    configure_authz(resolver=auth.resolve_principal, on_denied=audit.record_denied)
    configure_service_authz(
        resolver=auth.resolve_service_principal, on_denied=audit.record_service_denied
    )
    configure_client_auth(applications.authenticate_client)

    app.include_router(auth.auth_router, prefix=f"{API}/auth")
    app.include_router(applications.applications_router, prefix=f"{API}/applications")
    app.include_router(roles.service_access_router, prefix=f"{API}/applications")
    app.include_router(users.users_router, prefix=f"{API}/users")
    app.include_router(roles.roles_router, prefix=f"{API}/roles")
    app.include_router(audit.audit_router, prefix=f"{API}/audit")
    return app


app = create_app()
