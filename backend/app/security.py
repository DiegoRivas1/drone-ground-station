"""Acceso con token para exponer la estación a Internet (Cloudflare Tunnel).

- El token se define con la variable de entorno STATION_TOKEN o en el archivo
  backend/station_token.txt (no se sube a git). Se genera con: python tools/make_token.py
- Sin token configurado la estación funciona como antes (red local, sin login) y avisa.
- Con token:
    * La app Android lo manda en la cabecera  X-Station-Token  (o  Authorization: Bearer ...).
    * El panel web lo pide una vez y guarda una cookie HttpOnly (la usan fetch, WebSocket y descargas).
    * Quedan protegidos /api/*, /ws/*, /docs, /redoc y /openapi.json.
      Son públicos solo el panel estático (HTML/JS/CSS, sin datos), /api/health y /api/auth/*.
- Tras 10 intentos fallidos en 60 s desde un mismo origen se bloquea 60 s (429).
"""
from __future__ import annotations

import hmac
import os
import time
from http.cookies import SimpleCookie
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

COOKIE_NAME = "station_token"
COOKIE_MAX_AGE = 30 * 24 * 3600
TOKEN_FILE = Path(__file__).resolve().parent.parent / "station_token.txt"

MAX_FAILS = 10
WINDOW_S = 60.0
MIN_TOKEN_LEN = 16

PROTECTED_PREFIXES = ("/api", "/ws", "/docs", "/redoc", "/openapi.json")
PUBLIC_PATHS = ("/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/me")


def load_token() -> str | None:
    """Token configurado (variable de entorno o archivo) o None si no hay."""
    tok = os.getenv("STATION_TOKEN", "").strip()
    if not tok and TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
    return tok or None


def token_matches(expected: str, given: str | None) -> bool:
    if not given:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), given.encode("utf-8"))


class FailureLimiter:
    """Cuenta intentos fallidos por origen en una ventana deslizante."""

    def __init__(self, max_fails: int = MAX_FAILS, window_s: float = WINDOW_S):
        self.max_fails = max_fails
        self.window_s = window_s
        self._fails: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        now = time.monotonic()
        recent = [t for t in self._fails.get(key, []) if now - t < self.window_s]
        if recent:
            self._fails[key] = recent
        else:
            self._fails.pop(key, None)
        return recent

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.max_fails

    def retry_after(self, key: str) -> int:
        recent = self._recent(key)
        if not recent:
            return 0
        return max(1, int(self.window_s - (time.monotonic() - recent[0])))

    def fail(self, key: str) -> None:
        self._recent(key)
        self._fails.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)


limiter = FailureLimiter()


def _headers(scope: Scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


def client_key(scope: Scope) -> str:
    """Origen del cliente. Detrás de Cloudflare la IP real viene en CF-Connecting-IP."""
    h = _headers(scope)
    if h.get("cf-connecting-ip"):
        return h["cf-connecting-ip"]
    client = scope.get("client")
    return client[0] if client else "desconocido"


def credential(scope: Scope) -> str | None:
    """Token enviado por el cliente: cabecera de la app, Bearer o cookie del panel."""
    h = _headers(scope)
    if h.get("x-station-token"):
        return h["x-station-token"].strip()
    auth = h.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if h.get("cookie"):
        try:
            c = SimpleCookie()
            c.load(h["cookie"])
            if COOKIE_NAME in c:
                return c[COOKIE_NAME].value
        except Exception:  # cookie mal formada: se trata como ausente
            return None
    return None


def is_protected(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return False
    return any(path == p or path.startswith(p + "/") for p in PROTECTED_PREFIXES)


class TokenAuthMiddleware:
    """Middleware ASGI puro: sirve para HTTP y para WebSocket (BaseHTTPMiddleware no)."""

    def __init__(self, app: ASGIApp, token: str | None):
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        if self.token is None:
            state["authorized"] = True
            await self.app(scope, receive, send)
            return

        key = client_key(scope)
        given = credential(scope)
        ok = token_matches(self.token, given) and not limiter.blocked(key)
        state["authorized"] = ok

        if not is_protected(scope["path"]):
            await self.app(scope, receive, send)
            return

        if not ok:
            if given and not limiter.blocked(key) and not token_matches(self.token, given):
                limiter.fail(key)           # token presente pero incorrecto: cuenta como fallo
            await self._deny(scope, receive, send, key)
            return
        limiter.reset(key)
        await self.app(scope, receive, send)

    async def _deny(self, scope: Scope, receive: Receive, send: Send, key: str) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if limiter.blocked(key):
            resp = JSONResponse({"detail": "Demasiados intentos. Espera un minuto."}, status_code=429,
                                headers={"Retry-After": str(limiter.retry_after(key))})
        else:
            resp = JSONResponse({"detail": "No autorizado: falta el token de la estación."}, status_code=401)
        await resp(scope, receive, send)
