"""Almacenamiento de video H.264 recibido del teléfono.

El teléfono envía bloques numerados (seq) mientras graba. Se escriben en orden en
storage/videos/<recording_id>.h264. Si al terminar el teléfono detecta pérdidas,
sube el archivo completo, que reemplaza la copia de la PC.
"""
import re
import time
from pathlib import Path

from fastapi import HTTPException, Request

from app.config import VIDEOS_DIR
from app.database.db import connect, rows_to_dicts

_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,120}$")


def _now_ms() -> int:
    return int(time.time() * 1000)


def check_id(recording_id: str) -> str:
    """Evita rutas maliciosas: sólo letras, números, _ y -."""
    if not _ID_RE.match(recording_id):
        raise HTTPException(400, "recording_id inválido")
    return recording_id


def video_path(recording_id: str) -> Path:
    return VIDEOS_DIR / f"{check_id(recording_id)}.h264"


def _get(conn, recording_id: str):
    return conn.execute("SELECT * FROM videos WHERE id = ?", (recording_id,)).fetchone()


def append_chunk(recording_id: str, flight_id: str, seq: int, data: bytes) -> dict:
    """Agrega un bloque. Ignora duplicados (seq ya recibido). Devuelve el estado."""
    path = video_path(recording_id)
    now = _now_ms()
    with connect() as conn:
        row = _get(conn, recording_id)
        if row is None:
            conn.execute(
                """INSERT INTO videos (id, flight_id, filename, started_ms, updated_ms)
                   VALUES (?, ?, ?, ?, ?)""",
                (recording_id, flight_id or None, path.name, now, now),
            )
            last_seq = -1
            if path.exists():
                path.unlink()
        else:
            last_seq = row["last_seq"]

        if seq <= last_seq:
            return {"status": "duplicate", "last_seq": last_seq}

        gap = seq != last_seq + 1
        with open(path, "ab") as f:
            f.write(data)
        conn.execute(
            """UPDATE videos SET bytes = bytes + ?, chunks = chunks + 1, last_seq = ?,
                   updated_ms = ?, incomplete = CASE WHEN ? THEN 1 ELSE incomplete END
               WHERE id = ?""",
            (len(data), seq, now, int(gap), recording_id),
        )
    return {"status": "ok", "last_seq": seq, "gap": gap}


def complete(recording_id: str, flight_id: str, chunks: int, incomplete: bool) -> dict:
    check_id(recording_id)
    now = _now_ms()
    with connect() as conn:
        row = _get(conn, recording_id)
        if row is None:
            conn.execute(
                """INSERT INTO videos (id, flight_id, filename, started_ms, updated_ms, completed, incomplete)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (recording_id, flight_id or None, f"{recording_id}.h264", now, now, int(incomplete)),
            )
        else:
            conn.execute(
                """UPDATE videos SET completed = 1, updated_ms = ?,
                       incomplete = CASE WHEN ? THEN 1 ELSE incomplete END WHERE id = ?""",
                (now, int(incomplete), recording_id),
            )
        row = _get(conn, recording_id)
        return dict(row)


async def replace_with_upload(recording_id: str, flight_id: str, request: Request) -> dict:
    """Recibe el archivo completo desde el teléfono (streaming) y reemplaza la copia."""
    path = video_path(recording_id)
    tmp = path.with_suffix(".upload")
    size = 0
    with open(tmp, "wb") as f:
        async for part in request.stream():
            f.write(part)
            size += len(part)
    tmp.replace(path)
    now = _now_ms()
    with connect() as conn:
        if _get(conn, recording_id) is None:
            conn.execute(
                """INSERT INTO videos (id, flight_id, filename, bytes, started_ms, updated_ms, completed)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (recording_id, flight_id or None, path.name, size, now, now),
            )
        else:
            conn.execute(
                """UPDATE videos SET bytes = ?, completed = 1, incomplete = 0, updated_ms = ?
                   WHERE id = ?""", (size, now, recording_id))
    mp4 = path.with_suffix(".mp4")
    if mp4.exists():
        mp4.unlink()  # el MP4 anterior estaba incompleto
    return {"status": "ok", "bytes": size}


def flight_of(recording_id: str) -> str | None:
    with connect() as conn:
        row = _get(conn, check_id(recording_id))
    return row["flight_id"] if row else None


def _ffmpeg() -> str | None:
    from app.services.recorrido_service import ffmpeg_path  # import diferido: evita ciclos
    return ffmpeg_path()


def list_videos() -> list[dict]:
    with connect() as conn:
        rows = rows_to_dicts(conn.execute("SELECT * FROM videos ORDER BY started_ms DESC"))
    has_ffmpeg = _ffmpeg() is not None
    for r in rows:
        r["mp4_available"] = has_ffmpeg
    return rows


def to_mp4(recording_id: str) -> Path:
    """Convierte .h264 → .mp4 con ffmpeg (sin recodificar). Requiere ffmpeg en el PATH."""
    src = video_path(recording_id)
    if not src.exists():
        raise HTTPException(404, "Video no encontrado")
    dst = src.with_suffix(".mp4")
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    if not _ffmpeg():
        raise HTTPException(501, "ffmpeg no está disponible en la PC; descarga el .h264")
    from app.services.flight_archive import convert_to_mp4  # import diferido: evita ciclos
    try:
        convert_to_mp4(src, dst)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return dst


def delete_video(recording_id: str) -> None:
    path = video_path(recording_id)
    for p in (path, path.with_suffix(".mp4"), path.with_suffix(".upload")):
        if p.exists():
            p.unlink()
    with connect() as conn:
        conn.execute("DELETE FROM videos WHERE id = ?", (recording_id,))
