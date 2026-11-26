"""Pruebas del acceso con token.  Desde backend/:   python -m pytest tests -q
(requiere:  pip install pytest httpx)"""
import importlib

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

TOKEN = "token-de-prueba-" + "x" * 20


def _app(monkeypatch, token):
    if token is None:
        monkeypatch.delenv("STATION_TOKEN", raising=False)
        monkeypatch.setattr("app.security.TOKEN_FILE", __import__("pathlib").Path("/no/existe.txt"))
    else:
        monkeypatch.setenv("STATION_TOKEN", token)
    import app.security as sec
    sec.limiter._fails.clear()
    import app.main as main
    importlib.reload(main)
    return main.app


@pytest.fixture
def abierto(monkeypatch):
    with TestClient(_app(monkeypatch, None)) as c:
        yield c


@pytest.fixture
def cerrado(monkeypatch):
    with TestClient(_app(monkeypatch, TOKEN)) as c:
        yield c


def test_sin_token_todo_abierto(abierto):
    assert abierto.get("/api/flights").status_code == 200
    assert "ips" in abierto.get("/api/health").json()
    assert abierto.get("/api/auth/me").json() == {"required": False, "authorized": True}


def test_con_token_bloquea_api_y_docs(cerrado):
    assert cerrado.get("/api/flights").status_code == 401
    assert cerrado.get("/docs").status_code == 401
    assert cerrado.get("/openapi.json").status_code == 401
    assert cerrado.post("/api/events", json={}).status_code == 401


def test_con_token_panel_y_health_publicos(cerrado):
    assert cerrado.get("/").status_code == 200            # panel estático (sin datos)
    h = cerrado.get("/api/health")
    assert h.status_code == 200 and h.json() == {"status": "ok"}   # sin IPs locales
    assert cerrado.get("/api/auth/me").json() == {"required": True, "authorized": False}


def test_cabeceras_validas(cerrado):
    assert cerrado.get("/api/flights", headers={"X-Station-Token": TOKEN}).status_code == 200
    assert cerrado.get("/api/flights", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    assert "ips" in cerrado.get("/api/health", headers={"X-Station-Token": TOKEN}).json()


def test_token_incorrecto(cerrado):
    assert cerrado.get("/api/flights", headers={"X-Station-Token": "otro"}).status_code == 401
    assert cerrado.get("/api/flights", headers={"X-Station-Token": TOKEN[:-1]}).status_code == 401


def test_login_con_cookie(cerrado):
    assert cerrado.post("/api/auth/login", json={"token": "mal"}).status_code == 401
    r = cerrado.post("/api/auth/login", json={"token": TOKEN})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()
    assert cerrado.get("/api/flights").status_code == 200      # la cookie viaja sola
    assert cerrado.get("/api/auth/me").json()["authorized"] is True
    cerrado.post("/api/auth/logout")
    cerrado.cookies.clear()
    assert cerrado.get("/api/flights").status_code == 401


def test_cookie_secure_detras_de_cloudflare(cerrado):
    r = cerrado.post("/api/auth/login", json={"token": TOKEN}, headers={"X-Forwarded-Proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_websocket(cerrado):
    with pytest.raises(WebSocketDisconnect):
        with cerrado.websocket_connect("/ws/telemetry"):
            pass
    with cerrado.websocket_connect("/ws/telemetry", headers={"X-Station-Token": TOKEN}) as ws:
        ws.send_text("ping")


def test_limite_de_intentos(cerrado):
    for _ in range(9):
        assert cerrado.get("/api/flights", headers={"X-Station-Token": "malo"}).status_code == 401
    # el décimo fallo ya activa el bloqueo
    r = cerrado.get("/api/flights", headers={"X-Station-Token": "malo"})
    assert r.status_code == 429 and "retry-after" in r.headers
    # mientras dura el bloqueo, ni el token correcto entra desde ese origen (frena la fuerza bruta)
    assert cerrado.get("/api/flights", headers={"X-Station-Token": TOKEN}).status_code == 429
    assert cerrado.post("/api/auth/login", json={"token": TOKEN}).status_code == 429
    # otro cliente detrás del túnel (otra IP real) no se ve afectado
    ok = cerrado.get("/api/flights", headers={"X-Station-Token": TOKEN, "CF-Connecting-IP": "9.9.9.9"})
    assert ok.status_code == 200
