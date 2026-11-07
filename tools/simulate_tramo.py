"""Simula lo que hace la app al pulsar ● REC y ■ STOP: envía UN tramo al recorrido abierto.

Sirve para probar el flujo de recorridos/tramos/informe SIN el dron.

    python tools/simulate_tramo.py --video prueba.h264
    python tools/simulate_tramo.py --video prueba.mp4 --url http://192.168.1.50:8000

--video puede ser .h264 (como lo graba la app) o .mp4 (se extrae el H.264 con ffmpeg).
La telemetría se inventa: una línea recta a 3 m/s que dura lo mismo que el video.
Usa sólo la librería estándar (y ffmpeg / imageio-ffmpeg si el video es .mp4).
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def req(base, method, path, body=None, ctype="application/json"):
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    r = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ERROR {e.code}: {e.read().decode(errors='replace')}")


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def a_h264(video: Path, tmp: Path) -> tuple[Path, float]:
    """Devuelve el .h264 crudo y su duración aproximada en segundos."""
    if video.suffix.lower() == ".h264":
        h264 = video
    else:
        h264 = tmp / "video.h264"
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(video), "-an", "-c:v", "libx264",
                        "-preset", "veryfast", "-g", "30", "-r", "30", "-bsf:v", "h264_mp4toannexb",
                        "-f", "h264", str(h264)], check=True)
    # duración: contar fotogramas con ffmpeg
    r = subprocess.run([ffmpeg(), "-f", "h264", "-i", str(h264), "-f", "null", "-"],
                       capture_output=True, text=True)
    frames = 0
    for linea in r.stderr.splitlines():
        if "frame=" in linea:
            try:
                frames = int(linea.split("frame=")[1].split()[0])
            except (IndexError, ValueError):
                pass
    return h264, max(frames / 30.0, 2.0)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # flechas y tildes en la consola de Windows
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--lat", type=float, default=-16.4053)
    ap.add_argument("--lon", type=float, default=-71.5246)
    ap.add_argument("--rumbo", type=float, default=None, help="grados; por defecto distinto en cada tramo")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        h264, dur = a_h264(Path(args.video), tmp)
        print(f"Video: {h264.name}, ~{dur:.1f} s")

        # REC
        reserva = req(base, "POST", "/api/recorridos/activo/reservar-tramo", {"estado": "grabando"})
        n = reserva["tramo"]
        print(f"REC  → tramo {n} del recorrido '{reserva['recorrido']}'")

        inicio = int(time.time() * 1000)
        rumbo = math.radians(args.rumbo if args.rumbo is not None else (n * 70) % 360)
        lat0 = args.lat + (n - 1) * 0.0004
        filas = ["timestamp_ms,lat,lon,alt_m,tramo_id,heading_deg,speed_mps,battery_pct,satellites"]
        for i in range(int((dur + 1) * 5) + 1):          # 5 Hz, cubre todo el video
            t = i / 5.0
            d = 3.0 * t
            lat = lat0 + math.degrees(d * math.cos(rumbo) / 6371000)
            lon = args.lon + math.degrees(d * math.sin(rumbo) / (6371000 * math.cos(math.radians(lat0))))
            filas.append(f"{inicio + int(t * 1000)},{lat},{lon},{min(5.0, 1 + t)},0,"
                         f"{math.degrees(rumbo):.0f},3.0,{80 - n},14")
        (tmp / "telemetria.csv").write_text("\n".join(filas) + "\n", encoding="utf-8")
        (tmp / "meta.json").write_text(json.dumps({"video_start_epoch_ms": inicio}), encoding="utf-8")

        # STOP → subir
        ruta = f"/api/recorridos/{reserva['recorrido_id']}/tramos/{n}"
        for nombre, p in (("video.h264", h264), ("telemetria.csv", tmp / "telemetria.csv"),
                          ("meta.json", tmp / "meta.json")):
            req(base, "POST", f"{ruta}/archivos/{nombre}", p.read_bytes(), "application/octet-stream")
            print(f"STOP → subido {nombre}")
        t = req(base, "POST", f"{ruta}/completar")
        print(f"Tramo {n}: {t['estado']} (la PC convierte el video a MP4)")


if __name__ == "__main__":
    main()
