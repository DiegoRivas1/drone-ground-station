"""Estación de tierra para el DJI Mavic Air.

Arranque (desde la carpeta backend/):
    uvicorn app.main:app --host 0.0.0.0 --port 8000

- API REST bajo /api      (la usa la app Android y el panel)
- WebSockets bajo /ws     (tiempo real para el panel)
- Panel web en  /         (carpeta ../frontend)
- Documentación interactiva en /docs
"""
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import flights, live, recorridos, routes, telemetry, video, ws
from app.config import FRONTEND_DIR
from app.database.db import init_db


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
    from app.services.informe_service import diagnostico
    d = diagnostico()
    print(f"  Análisis (inspeccion-dron): {'OK' if d['inspeccion_encontrado'] else 'NO ENCONTRADO'} -> {d['inspeccion_dir']}")
    print(f"  Python del análisis: {d['python']}")
    print(f"  ffmpeg: {'OK' if d['ffmpeg'] else 'NO'} | IA ({d['proveedor']}): "
          f"{'clave OK' if d['clave_configurada'] else 'sin clave (informe sin redacción con IA)'}")
    print("================================\n")
    yield


app = FastAPI(title="Drone Ground Station", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "ips": _local_ips()}


app.include_router(telemetry.router)
app.include_router(flights.router)
app.include_router(routes.router)
app.include_router(video.router)
app.include_router(live.router)
app.include_router(recorridos.router)
app.include_router(ws.router)

# El panel web se monta al final para no tapar /api ni /ws.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
