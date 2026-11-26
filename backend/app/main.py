"""Estación de tierra para el DJI Mavic Air.

Arranque (desde la carpeta backend/):
    uvicorn app.main:app --host 0.0.0.0 --port 8000

- API REST bajo /api      (la usa la app Android y el panel)
- WebSockets bajo /ws     (tiempo real para el panel)
- Panel web en  /         (carpeta ../frontend)
- Documentación interactiva en /docs
"""
import os
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import auth, flights, live, recorridos, routes, telemetry, video, ws
from app.config import FRONTEND_DIR
from app.database.db import init_db
from app.security import MIN_TOKEN_LEN, TokenAuthMiddleware, load_token


def _local_ips() -> list[str]:
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ips = _local_ips()
    print("\n=== Estación de tierra lista ===")
    for ip in ips:
        print(f"  Panel:          http://{ip}:8000")
        print(f"  En la app (PC): http://{ip}:8000")
    tok = load_token()
    if tok is None:
        print("  Acceso: SIN TOKEN (solo para red local). NO la expongas a Internet / Cloudflare.")
        print("          Crea uno con:  python tools/make_token.py")
    else:
        aviso = "  [corto: usa uno de 16+ caracteres]" if len(tok) < MIN_TOKEN_LEN else ""
        print(f"  Acceso: con token (X-Station-Token en la app, login en el panel){aviso}")
    from app.services.informe_service import diagnostico
    d = diagnostico()
    print(f"  Análisis (inspeccion-dron): {'OK' if d['inspeccion_encontrado'] else 'NO ENCONTRADO'} -> {d['inspeccion_dir']}")
    print(f"  Python del análisis: {d['python']}")
    print(f"  ffmpeg: {'OK' if d['ffmpeg'] else 'NO'} | IA ({d['proveedor']}): "
          f"{'clave OK' if d['clave_configurada'] else 'sin clave (informe sin redacción con IA)'}")
    print("================================\n")
    yield


app = FastAPI(title="Drone Ground Station", version="1.0", lifespan=lifespan)

# El panel se sirve desde este mismo servidor (mismo origen), así que CORS no hace falta.
# Solo se activa si defines STATION_CORS_ORIGINS="https://a.com,https://b.com".
_cors = [o.strip() for o in os.getenv("STATION_CORS_ORIGINS", "").split(",") if o.strip()]
if _cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Va al final para quedar como capa externa (se ejecuta primero en cada petición).
app.add_middleware(TokenAuthMiddleware, token=load_token())


@app.middleware("http")
async def sin_cache_para_el_panel(request, call_next):
    """El navegador revalida HTML/JS/CSS en cada carga: así un cambio del panel se ve sin Ctrl+F5."""
    resp = await call_next(request)
    if not request.url.path.startswith(("/api", "/ws")) and resp.headers.get("content-type", "").startswith(
            ("text/html", "text/css", "text/javascript", "application/javascript")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/api/health")
def health(request: Request):
    out = {"status": "ok"}
    if request.scope.get("state", {}).get("authorized"):   # las IPs locales solo para quien tiene token
        out["ips"] = _local_ips()
    return out


app.include_router(auth.router)
app.include_router(telemetry.router)
app.include_router(flights.router)
app.include_router(routes.router)
app.include_router(video.router)
app.include_router(live.router)
app.include_router(recorridos.router)
app.include_router(ws.router)

# El panel web se monta al final para no tapar /api ni /ws.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
