"""Rutas y parámetros del servidor."""
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

STORAGE_DIR = BACKEND_DIR / "storage"
VIDEOS_DIR = STORAGE_DIR / "videos"
FLIGHTS_DIR = STORAGE_DIR / "flights"
DB_PATH = STORAGE_DIR / "ground_station.db"

FRONTEND_DIR = PROJECT_DIR / "frontend"

# Tamaño máximo del búfer "último GOP" que se envía a un visor nuevo del video en vivo.
LIVE_GOP_MAX_BYTES = 4 * 1024 * 1024

for d in (STORAGE_DIR, VIDEOS_DIR, FLIGHTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Recorridos / tramos e informe
# ---------------------------------------------------------------------------
import os
import sys

RECORRIDOS_DIR = STORAGE_DIR / "recorridos"
RECORRIDOS_DIR.mkdir(parents=True, exist_ok=True)


def _buscar_inspeccion() -> Path:
    """Carpeta del proyecto de análisis (dron_project_reconocimiento/inspeccion-dron)."""
    env = os.getenv("INSPECCION_DIR")
    if env:
        return Path(env)
    candidatos = [
        PROJECT_DIR.parent / "dron_project_reconocimiento" / "inspeccion-dron",
        PROJECT_DIR.parent / "inspeccion-dron",
        Path.home() / "dron_project_reconocimiento" / "inspeccion-dron",
    ]
    for c in candidatos:
        if (c / "01_procesar_video.py").exists():
            return c
    return candidatos[0]


INSPECCION_DIR = _buscar_inspeccion()


def _python_inspeccion() -> str:
    """Python del venv del proyecto de análisis (tiene YOLO, pandas...)."""
    env = os.getenv("INSPECCION_PYTHON")
    if env:
        return env
    for p in (INSPECCION_DIR / "venv" / "Scripts" / "python.exe",
              INSPECCION_DIR / "venv" / "bin" / "python",
              INSPECCION_DIR / ".venv" / "Scripts" / "python.exe",
              INSPECCION_DIR / ".venv" / "bin" / "python"):
        if p.exists():
            return str(p)
    return sys.executable


INSPECCION_PYTHON = _python_inspeccion()

# FPS con que se interpreta el .h264 crudo al convertirlo a MP4 (Mavic Air: 30).
VIDEO_FPS = float(os.getenv("VIDEO_FPS", "30"))
# Corrección de sincronía video/telemetría (la transmisión llega ~200 ms tarde).
VIDEO_OFFSET_MS = int(os.getenv("VIDEO_OFFSET_MS", "0"))
