"""Carpeta por vuelo: storage/flights/<flight_id>/

    telemetria.csv   telemetría + eventos del vuelo (mismo formato que /export.csv)
    video.mp4        video del vuelo, convertido automáticamente desde el H.264
                     (si hubo varias grabaciones: video_2.mp4, video_3.mp4, ...)
    resumen.json     inicio/fin, muestras, eventos, archivos

La app crea un vuelo nuevo en cada despegue y lo cierra al aterrizar (evento FLIGHT_END).
El archivo se genera al recibir FLIGHT_END y otra vez cuando termina de llegar el video,
así que el orden en que lleguen no importa. Se puede regenerar con
POST /api/flights/{id}/archive.
"""
import json
import logging
import re
import subprocess
import threading
from pathlib import Path

from fastapi import HTTPException

from app.config import FLIGHTS_DIR, VIDEO_FPS
from app.database.db import connect
from app.services import h264_params, telemetry_service, video_service
from app.services.recorrido_service import ffmpeg_path

log = logging.getLogger("flight_archive")

# Un archivado a la vez por vuelo (FLIGHT_END y fin de video pueden llegar juntos).
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(flight_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(flight_id, threading.Lock())


def flight_dir(flight_id: str) -> Path:
    video_service.check_id(flight_id)  # mismas reglas: sólo letras, números, _ y -
    return FLIGHTS_DIR / flight_id


# Sube este número si cambia la conversión: los MP4 hechos con una versión anterior
# se regeneran solos (la v1 copiaba sin recodificar y salían archivos que no abren).
MP4_VERSION = 3

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def convert_to_mp4(src: Path, dst: Path) -> None:
    """H.264 crudo del dron → MP4 que abre en cualquier reproductor.

    SIEMPRE se recodifica. Copiar el H.264 tal cual (-c copy) "funciona" pero deja un
    MP4 roto: la grabación empieza a mitad de un GOP (sin fotograma clave) y el flujo
    crudo no trae marcas de tiempo, así que Windows/navegadores dicen "error".
    Al recodificar, ffmpeg descarta lo que no se puede decodificar, empieza en el
    primer fotograma clave y genera tiempos limpios a VIDEO_FPS.
    Perfil Main + yuv420p + faststart = compatible con Windows, móviles y navegadores.
    """
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("ffmpeg no disponible (instala requirements.txt: imageio-ffmpeg)")
    tmp = dst.with_suffix(".tmp.mp4")
    fps = str(VIDEO_FPS)
    fixed = None
    if not h264_params.has_params(src):
        # Grabación sin SPS/PPS: usar los de otra grabación del mismo dron.
        header = h264_params.find_header(exclude=src)
        if header is None:
            raise RuntimeError(
                f"{src.name} no contiene SPS/PPS y no hay otra grabación de la que tomarlos. "
                "Actualiza la app (ya los añade al empezar a grabar) y graba de nuevo.")
        fixed = src.with_suffix(".fixed.h264")
        h264_params.write_with_header(src, fixed, header)
        log.info("%s: sin SPS/PPS, se añadieron los de otra grabación", src.name)
    cmd = [ff, "-y", "-loglevel", "error",
           "-err_detect", "ignore_err", "-fflags", "+genpts+discardcorrupt",
           # El Mavic Air casi no manda fotogramas clave (intra refresh): sin showall
           # ffmpeg descarta todo lo anterior al primer keyframe (o el video entero).
           "-flags2", "+showall",
           "-r", fps, "-f", "h264", "-i", str(fixed or src),
           "-an", "-fps_mode", "cfr", "-r", fps,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-pix_fmt", "yuv420p", "-profile:v", "main", "-level", "4.0",
           "-movflags", "+faststart", str(tmp)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    finally:
        if fixed is not None and fixed.exists():
            fixed.unlink()
    seconds = _duration(ff, tmp) if tmp.exists() else 0.0
    if r.returncode != 0 or seconds <= 0:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(f"ffmpeg no pudo convertir {src.name}: {(r.stderr or '')[-400:]}")
    tmp.replace(dst)
    log.info("MP4 listo: %s (%.1f s)", dst, seconds)


def _duration(ff: str, path: Path) -> float:
    """Duración del MP4 resultante (0 si no se puede leer = archivo inválido)."""
    r = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=60)
    m = _DURATION_RE.search(r.stderr or "")
    if not m:
        return 0.0
    h, mnt, sec = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(sec)


def _videos_of(flight_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE flight_id = ? AND completed = 1 ORDER BY started_ms",
            (flight_id,)).fetchall()
    return [dict(r) for r in rows]


def _previous_mp4_version(d: Path) -> int:
    try:
        return int(json.loads((d / "resumen.json").read_text(encoding="utf-8")).get("mp4_version", 1))
    except Exception:
        return 1


def archive_flight(flight_id: str, force: bool = False) -> dict:
    """Escribe/actualiza la carpeta del vuelo. Idempotente.

    force=True (botón "Guardar carpeta") rehace también los MP4.
    """
    d = flight_dir(flight_id)
    flight = telemetry_service.get_flight(flight_id)
    if not flight:
        raise HTTPException(404, "Vuelo no encontrado")
    with _lock_for(flight_id):
        d.mkdir(parents=True, exist_ok=True)
        (d / "telemetria.csv").write_text(telemetry_service.export_csv(flight_id), encoding="utf-8")

        errors = []
        mp4s = []
        redo = force or _previous_mp4_version(d) < MP4_VERSION
        for i, v in enumerate(_videos_of(flight_id), start=1):
            src = video_service.video_path(v["id"])
            if not src.exists() or src.stat().st_size == 0:
                continue
            dst = d / ("video.mp4" if i == 1 else f"video_{i}.mp4")
            if not redo and dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
                mp4s.append(dst.name)
                continue
            try:
                convert_to_mp4(src, dst)
                mp4s.append(dst.name)
            except Exception as e:  # el CSV ya está guardado aunque falle el video
                log.warning("Vuelo %s: %s", flight_id, e)
                errors.append(str(e))

        events = telemetry_service.get_events(flight_id)
        resumen = {
            "flight_id": flight_id,
            "drone_model": flight.get("drone_model"),
            "started_at_ms": flight.get("started_at_ms"),
            "last_seen_ms": flight.get("last_seen_ms"),
            "samples": flight.get("samples"),
            "events": len(events),
            "ended": any(e["type"] == "FLIGHT_END" for e in events),
            "videos": mp4s,
            "mp4_version": MP4_VERSION,
            "errors": errors,
        }
        (d / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**resumen, "files": list_files(flight_id)}


def archive_quietly(flight_id: str) -> None:
    """Para BackgroundTasks: nunca lanza."""
    try:
        if flight_id:
            archive_flight(flight_id)
    except Exception as e:
        log.warning("No se pudo archivar el vuelo %s: %s", flight_id, e)


def list_files(flight_id: str) -> list[str]:
    try:
        d = flight_dir(flight_id)
    except HTTPException:
        return []
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_file() and ".tmp." not in p.name)


def file_path(flight_id: str, name: str) -> Path:
    if name not in list_files(flight_id):
        raise HTTPException(404, "Archivo no encontrado")
    return flight_dir(flight_id) / name
