"""Inicio de sesión del panel web (cookie HttpOnly con el token de la estación)."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.security import (COOKIE_MAX_AGE, COOKIE_NAME, client_key, limiter, load_token, token_matches)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    token: str


def _https(request: Request) -> bool:
    # Detrás de Cloudflare el servidor local ve http, pero el navegador usa https.
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


@router.get("/me")
def me(request: Request):
    """El panel lo consulta al cargar: ¿hace falta token y ya lo tengo?"""
    required = load_token() is not None
    return {"required": required, "authorized": bool(request.scope.get("state", {}).get("authorized"))}


@router.post("/login")
def login(body: Login, request: Request):
    expected = load_token()
    if expected is None:
        return {"required": False, "authorized": True}
    key = client_key(request.scope)
    if limiter.blocked(key):
        return JSONResponse({"detail": "Demasiados intentos. Espera un minuto."}, status_code=429,
                            headers={"Retry-After": str(limiter.retry_after(key))})
    if not token_matches(expected, body.token.strip()):
        limiter.fail(key)
        return JSONResponse({"detail": "Token incorrecto."}, status_code=401)
    limiter.reset(key)
    resp = JSONResponse({"required": True, "authorized": True})
    resp.set_cookie(COOKIE_NAME, body.token.strip(), max_age=COOKIE_MAX_AGE, httponly=True,
                    samesite="strict", secure=_https(request), path="/")
    return resp


@router.post("/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp
