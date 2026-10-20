"""Piezas del flujo de login BFF: `state` + PKCE y su cookie firmada.

Cookie de flujo (corta, HttpOnly): `base64url(json) . base64url(HMAC-SHA256)`
con `state`, `code_verifier`, `jkt` (la llave DPoP del navegador que inicio el
flujo) y `exp`. En el callback se exige `state` igual al de la URL y la prueba
DPoP del mismo `jkt`: un code o una cookie de otro navegador no sirve. El
`code_verifier` es visible para el dueno del navegador, lo cual es aceptable:
PKCE protege contra quien intercepta el code, no contra el propio navegador.
"""

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from urllib.parse import urlencode

from leo_sdk.crypto import (
    b64url_decode,
    b64url_encode,
    constant_time_equals,
    random_token,
    sha256_b64url,
)


class FlowCookieError(Exception):
    """Cookie de flujo ausente, alterada o expirada."""


@dataclass(frozen=True)
class AuthFlow:
    state: str
    code_verifier: str
    jkt: str

    @property
    def code_challenge(self) -> str:
        return pkce_challenge(self.code_verifier)


def pkce_challenge(code_verifier: str) -> str:
    """`BASE64URL(SHA256(verifier))` (RFC 7636, S256)."""
    return sha256_b64url(code_verifier)


def new_flow(*, jkt: str) -> AuthFlow:
    return AuthFlow(state=random_token(), code_verifier=random_token(), jkt=jkt)


def build_authorize_url(
    leo_url: str, *, client_id: str, redirect_uri: str, flow: AuthFlow
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": flow.state,
            "code_challenge": flow.code_challenge,
            "code_challenge_method": "S256",
            "dpop_jkt": flow.jkt,
        }
    )
    return f"{leo_url.rstrip('/')}/authorize?{query}"


class FlowCookie:
    def __init__(
        self,
        key: bytes,
        *,
        ttl_seconds: int = 600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._key = key
        self._ttl = ttl_seconds
        self._clock = clock

    def _mac(self, body: str) -> str:
        return b64url_encode(
            hmac.new(self._key, body.encode("ascii"), hashlib.sha256).digest()
        )

    def dumps(self, flow: AuthFlow) -> str:
        data = {**asdict(flow), "exp": int(self._clock()) + self._ttl}
        body = b64url_encode(json.dumps(data, separators=(",", ":")).encode())
        return f"{body}.{self._mac(body)}"

    def loads(self, value: str | None) -> AuthFlow:
        if not value or value.count(".") != 1:
            raise FlowCookieError("cookie de flujo ausente o malformada")
        body, mac = value.split(".")
        if not constant_time_equals(self._mac(body), mac):
            raise FlowCookieError("cookie de flujo alterada")
        try:
            data = json.loads(b64url_decode(body))
            exp = int(data["exp"])
            flow = AuthFlow(data["state"], data["code_verifier"], data["jkt"])
        except (ValueError, KeyError, TypeError) as exc:
            raise FlowCookieError("cookie de flujo malformada") from exc
        if self._clock() >= exp:
            raise FlowCookieError("cookie de flujo expirada")
        return flow
