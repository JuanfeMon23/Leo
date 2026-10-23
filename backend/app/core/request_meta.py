"""Metadatos de la peticion para sesiones y auditoria: ip, user-agent y
`request_id` (header `X-Request-ID` del cliente si es valido, si no uno
nuevo; se devuelve en la respuesta).

La ip sale de `app.core.client_ip.client_ip` (respeta `LEO_TRUSTED_PROXIES`).
"""

import re
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.client_ip import client_ip

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
USER_AGENT_MAX_LENGTH = 512


@dataclass(frozen=True)
class RequestMeta:
    ip: str | None
    user_agent: str | None
    request_id: str | None


def request_meta(request: Request) -> RequestMeta:
    agent = request.headers.get("user-agent")
    return RequestMeta(
        ip=client_ip(request),
        user_agent=agent[:USER_AGENT_MAX_LENGTH] if agent else None,
        request_id=getattr(request.state, "request_id", None),
    )


Meta = Annotated[RequestMeta, Depends(request_meta)]


class RequestIdMiddleware:
    """Asigna `request.state.request_id` y lo devuelve en `X-Request-ID`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = (
            dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        )
        request_id = incoming if _REQUEST_ID_PATTERN.match(incoming) else uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_id)
