"""Recorridos y tramos.

Un RECORRIDO es una carpeta autocontenida:

    storage/recorridos/<id>/
        recorrido.json                 estado (tramos, informe)
        tramo_01/  video.h264  video.mp4  telemetria.csv  meta.json
        tramo_02/  ...
        analisis/                      salida del análisis y el informe

Cada TRAMO es la pareja (video, telemetría) de una grabación REC → STOP del teléfono.

Estados de un tramo:
    esperando  → la PC pulsó NUEVO TRAMO, el teléfono aún no graba
    grabando   → el teléfono pulsó REC
    subiendo   → el teléfono pulsó STOP y está enviando los archivos
    procesando → archivos recibidos; convirtiendo el video a MP4
    recibido   → listo para el informe
    error      → algo falló (ver campo "error")
    descartado → el usuario lo excluyó del informe
"""
import csv
import json
import math
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from app.config import RECORRIDOS_DIR

ARCHIVOS_TRAMO = {"video.h264", "telemetria.csv", "meta.json"}
_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,80}$")
_lock = threading.RLock()


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Persistencia (un JSON por recorrido)
# ---------------------------------------------------------------------------

def _dir(rid: str) -> Path:
    if not _ID_RE.match(rid):
        raise HTTPException(400, "id de recorrido inválido")
    return RECORRIDOS_DIR / rid


def _tramo_dir(rid: str, n: int) -> Path:
    return _dir(rid) / f"tramo_{n:02d}"


def _load(rid: str) -> dict:
    path = _dir(rid) / "recorrido.json"
    if not path.exists():
        raise HTTPException(404, "Recorrido no encontrado")
    return json.loads(path.read_text(encoding="utf-8"))


def _save(rec: dict) -> None:
    path = _dir(rec["id"]) / "recorrido.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _tramo(rec: dict, n: int) -> dict:
    for t in rec["tramos"]:
        if t["n"] == n:
            return t
    raise HTTPException(404, f"Tramo {n} no encontrado")


def _slug(texto: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", texto.strip())[:40].strip("_")
    return s or "recorrido"


# ---------------------------------------------------------------------------
# Recorridos
# ---------------------------------------------------------------------------

def listar() -> list[dict]:
    out = []
    for p in sorted(RECORRIDOS_DIR.glob("*/recorrido.json"), reverse=True):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({
            "id": rec["id"], "nombre": rec["nombre"], "estado": rec["estado"],
            "creado_ms": rec["creado_ms"],
            "tramos": len([t for t in rec["tramos"] if t["estado"] != "descartado"]),
            "informe": rec.get("informe", {}).get("estado", "no_generado"),
        })
    out.sort(key=lambda r: r["creado_ms"], reverse=True)
    return out


def obtener(rid: str) -> dict:
    with _lock:
        return _load(rid)


def activo() -> dict | None:
    """El recorrido ABIERTO (sólo puede haber uno)."""
    with _lock:
        for r in listar():
            if r["estado"] == "abierto":
                return _load(r["id"])
    return None


def crear(nombre: str) -> dict:
    with _lock:
        # Sólo un recorrido abierto: el anterior se finaliza automáticamente.
        prev = activo()
        if prev:
            prev["estado"] = "finalizado"
            prev["finalizado_ms"] = _now_ms()
            _save(prev)

        nombre = nombre.strip() or "Recorrido"
        base = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + _slug(nombre)
        rid = base
        i = 2
        while (RECORRIDOS_DIR / rid).exists():
            rid = f"{base}_{i}"
            i += 1
        (RECORRIDOS_DIR / rid).mkdir(parents=True)
        rec = {
            "id": rid, "nombre": nombre, "estado": "abierto",
            "creado_ms": _now_ms(), "finalizado_ms": None,
            "tramos": [],
            "informe": {"estado": "no_generado"},
        }
        _save(rec)
        return rec


def finalizar(rid: str) -> dict:
    with _lock:
        rec = _load(rid)
        rec["estado"] = "finalizado"
        rec["finalizado_ms"] = _now_ms()
        # Un tramo que nunca empezó a grabarse no tiene sentido en el informe.
        rec["tramos"] = [t for t in rec["tramos"] if t["estado"] != "esperando"]
        _save(rec)
        return rec


def reabrir(rid: str) -> dict:
    with _lock:
        prev = activo()
        if prev and prev["id"] != rid:
            prev["estado"] = "finalizado"
            prev["finalizado_ms"] = _now_ms()
            _save(prev)
        rec = _load(rid)
        rec["estado"] = "abierto"
        rec["finalizado_ms"] = None
        _save(rec)
        return rec


# ---------------------------------------------------------------------------
# Tramos
# ---------------------------------------------------------------------------

def _nuevo_tramo(rec: dict, estado: str) -> dict:
    n = max([t["n"] for t in rec["tramos"]], default=0) + 1
    t = {"n": n, "estado": estado, "creado_ms": _now_ms(), "recibido_ms": None,
         "video_bytes": 0, "muestras_gps": 0, "duracion_s": None, "distancia_m": None,
         "error": None, "aviso": None}
    rec["tramos"].append(t)
    _tramo_dir(rec["id"], n).mkdir(parents=True, exist_ok=True)
    return t


def nuevo_tramo(rid: str) -> dict:
    """Botón NUEVO TRAMO de la PC. Si ya hay uno esperando, devuelve ese."""
    with _lock:
        rec = _load(rid)
        if rec["estado"] != "abierto":
            raise HTTPException(409, "El recorrido está finalizado")
        for t in rec["tramos"]:
            if t["estado"] in ("esperando", "grabando"):
                return t
        t = _nuevo_tramo(rec, "esperando")
        _save(rec)
        return t


def reservar_tramo(estado: str) -> dict:
    """Lo llama el teléfono al pulsar REC (estado=grabando) o al subir (estado=subiendo).

    Usa el tramo que la PC dejó 'esperando'; si no hay, crea uno nuevo.
    """
    if estado not in ("grabando", "subiendo"):
        raise HTTPException(400, "estado inválido")
    with _lock:
        rec = activo()
        if rec is None:
            raise HTTPException(409, "No hay un recorrido abierto en la PC. Pulsa NUEVO RECORRIDO.")
        t = next((x for x in rec["tramos"] if x["estado"] == "esperando"), None)
        if t is None:
            t = _nuevo_tramo(rec, estado)
        t["estado"] = estado
        _save(rec)
        return {"recorrido_id": rec["id"], "recorrido": rec["nombre"], "tramo": t["n"]}


def marcar(rid: str, n: int, estado: str) -> None:
    with _lock:
        rec = _load(rid)
        _tramo(rec, n)["estado"] = estado
        _save(rec)


def descartar(rid: str, n: int) -> dict:
    with _lock:
        rec = _load(rid)
        t = _tramo(rec, n)
        t["estado"] = "descartado"
        _save(rec)
        return t


async def guardar_archivo(rid: str, n: int, nombre: str, request) -> int:
    if nombre not in ARCHIVOS_TRAMO:
        raise HTTPException(400, f"Archivo no permitido: {nombre}")
    with _lock:
        rec = _load(rid)
        t = _tramo(rec, n)
        if t["estado"] == "descartado":
            raise HTTPException(409, "Tramo descartado")
        if t["estado"] in ("esperando", "grabando"):
            t["estado"] = "subiendo"
            _save(rec)
    destino = _tramo_dir(rid, n) / nombre
    tmp = destino.with_suffix(destino.suffix + ".part")
    size = 0
    with open(tmp, "wb") as f:
        async for part in request.stream():
            f.write(part)
            size += len(part)
    tmp.replace(destino)
    return size


def completar(rid: str, n: int) -> dict:
    """El teléfono terminó de subir: validar y convertir el video en segundo plano."""
    d = _tramo_dir(rid, n)
    faltan = [a for a in ("video.h264", "telemetria.csv") if not (d / a).exists()]
    with _lock:
        rec = _load(rid)
        t = _tramo(rec, n)
        if faltan:
            t["estado"] = "error"
            t["error"] = "Faltan archivos: " + ", ".join(faltan)
            _save(rec)
            return t
        t["estado"] = "procesando"
        t["recibido_ms"] = _now_ms()
        t["error"] = None
        _save(rec)
    threading.Thread(target=_procesar_tramo, args=(rid, n), daemon=True).start()
    return t


# ---------------------------------------------------------------------------
# Procesamiento de un tramo recibido
# ---------------------------------------------------------------------------

def ffmpeg_path() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # incluido en requirements.txt: ffmpeg sin instalar nada aparte
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _haversine(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _normalizar_telemetria(path: Path, n: int) -> tuple[int, float | None, float | None]:
    """Deja el CSV en el formato del análisis (timestamp_ms,lat,lon,alt_m,tramo_id,...),
    pone tramo_id = n y elimina filas sin posición válida."""
    with open(path, newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    validas = []
    for r in filas:
        try:
            ts = int(float(r["timestamp_ms"]))
            lat, lon = float(r["lat"]), float(r["lon"])
            alt = float(r.get("alt_m") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)) or (lat == 0 and lon == 0):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        r.update(timestamp_ms=ts, lat=lat, lon=lon, alt_m=alt if math.isfinite(alt) else 0.0, tramo_id=n)
        validas.append(r)
    validas.sort(key=lambda r: r["timestamp_ms"])

    columnas = ["timestamp_ms", "lat", "lon", "alt_m", "tramo_id"]
    extra = [c for c in (filas[0].keys() if filas else []) if c not in columnas]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columnas + extra, extrasaction="ignore")
        w.writeheader()
        w.writerows(validas)

    if len(validas) < 2:
        return len(validas), None, None
    dur = (validas[-1]["timestamp_ms"] - validas[0]["timestamp_ms"]) / 1000.0
    dist = 0.0
    for a, b in zip(validas, validas[1:]):
        d = _haversine(a["lat"], a["lon"], b["lat"], b["lon"])
        if d >= 0.3:  # ignorar el ruido del GPS en hover
            dist += d
    return len(validas), dur, dist


def _procesar_tramo(rid: str, n: int) -> None:
    d = _tramo_dir(rid, n)
    error = None
    aviso = None
    muestras, dur, dist = 0, None, None
    try:
        muestras, dur, dist = _normalizar_telemetria(d / "telemetria.csv", n)
        if muestras < 2:
            aviso = ("Telemetría sin posición GPS (¿vuelo en interior?). "
                     "Este tramo no se puede analizar.")
        if not (d / "meta.json").exists():
            aviso = (aviso + " " if aviso else "") + "Sin meta.json: se sincroniza con la 1ª muestra de telemetría."

        # Misma conversión que los vuelos: recodifica, tolera la falta de fotogramas
        # clave del Mavic Air y repone SPS/PPS si la grabación no los trae.
        from app.services.flight_archive import convert_to_mp4  # import diferido: evita ciclos
        convert_to_mp4(d / "video.h264", d / "video.mp4")
    except Exception as e:  # noqa: BLE001 - se informa en el panel
        error = str(e)

    with _lock:
        rec = _load(rid)
        t = _tramo(rec, n)
        t["muestras_gps"] = muestras
        t["duracion_s"] = round(dur, 1) if dur is not None else None
        t["distancia_m"] = round(dist, 1) if dist is not None else None
        t["video_bytes"] = (d / "video.h264").stat().st_size if (d / "video.h264").exists() else 0
        t["aviso"] = aviso
        t["error"] = error
        if t["estado"] != "descartado":
            t["estado"] = "error" if error else "recibido"
        _save(rec)


def archivo_tramo(rid: str, n: int, nombre: str) -> Path:
    if nombre not in ARCHIVOS_TRAMO | {"video.mp4"}:
        raise HTTPException(400, "Archivo no permitido")
    p = _tramo_dir(rid, n) / nombre
    if not p.exists():
        raise HTTPException(404, "Archivo no encontrado")
    return p


def actualizar_informe(rid: str, **campos) -> None:
    with _lock:
        rec = _load(rid)
        rec.setdefault("informe", {}).update(campos)
        _save(rec)


def directorio(rid: str) -> Path:
    return _dir(rid)
