"""Simulador de la app Android: envía telemetría, eventos y (opcional) video al servidor.

Sirve para probar el servidor y el panel SIN el dron.

    python tools/simulate_drone.py                       # telemetría + eventos
    python tools/simulate_drone.py --video vuelo.h264    # además, envía un .h264 como "en vivo"
    python tools/simulate_drone.py --url http://192.168.1.50:8000 --seconds 60

Usa sólo la librería estándar de Python.
"""
import argparse
import json
import math
import time
import urllib.request
from datetime import datetime


def post(url: str, body: bytes, content_type: str) -> dict:
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read() or b"null")


def post_json(base: str, path: str, data: dict) -> dict:
    return post(base + path, json.dumps(data).encode(), "application/json")


def sample(t: float, lat0: float, lon0: float) -> dict:
    """Vuelo circular de 10 m de radio a 5 m de altura."""
    r = 10.0
    w = 2 * math.pi / 40.0  # una vuelta cada 40 s
    north = r * math.sin(w * t)
    east = r * (1 - math.cos(w * t))
    lat = lat0 + math.degrees(north / 6371000)
    lon = lon0 + math.degrees(east / (6371000 * math.cos(math.radians(lat0))))
    vn = r * w * math.cos(w * t)
    ve = r * w * math.sin(w * t)
    return {
        "timestamp_ms": int(time.time() * 1000),
        "latitude": lat, "longitude": lon,
        "altitude_m": min(5.0, t * 1.0),
        "velocity_x": vn, "velocity_y": ve, "velocity_z": 0.0,
        "speed_mps": math.hypot(vn, ve),
        "heading_deg": (math.degrees(math.atan2(ve, vn)) + 360) % 360,
        "battery_pct": max(20, 95 - int(t / 10)),
        "is_flying": True, "motors_on": True,
        "satellites": 14, "gps_level": 5, "flight_mode": "GPS_ATTI",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--lat", type=float, default=-16.4090)
    ap.add_argument("--lon", type=float, default=-71.5375)
    ap.add_argument("--video", help="archivo .h264 para enviar en bloques como video en vivo")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    flight_id = "sim_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    print("Health:", json.loads(urllib.request.urlopen(base + "/api/health", timeout=5).read()))
    print("Vuelo simulado:", flight_id)

    def event(kind: str, details: str = "") -> None:
        post_json(base, "/api/events", {
            "flight_id": flight_id, "type": kind, "details": details,
            "timestamp_ms": int(time.time() * 1000), "telemetry": sample(0, args.lat, args.lon),
        })

    event("DRONE_CONNECTED", "SIMULADOR")
    event("TAKEOFF_START", "simulado")

    video = open(args.video, "rb") if args.video else None
    rec_id = flight_id + "_rec_sim"
    seq = 0
    start = time.time()
    batch = []
    try:
        while (t := time.time() - start) < args.seconds:
            batch.append(sample(t, args.lat, args.lon))
            if len(batch) >= 2:  # 2 Hz, lote por segundo, como la app
                post_json(base, "/api/telemetry", {"flight_id": flight_id, "drone_model": "SIMULADOR", "samples": batch})
                batch = []
            if video:
                chunk = video.read(60_000)  # ~ medio segundo de video
                if not chunk:
                    video.seek(0)
                    chunk = video.read(60_000)
                post(f"{base}/api/video/{rec_id}/chunk?flight_id={flight_id}&seq={seq}", chunk, "application/octet-stream")
                seq += 1
            time.sleep(0.5)
        event("MANUAL_STOP", "fin de la simulación")
        event("LANDED")
        if video:
            post_json(base, f"/api/video/{rec_id}/complete?flight_id={flight_id}", {"chunks": seq, "incomplete": False})
    finally:
        if video:
            video.close()
    print("Listo. Abre el panel:", base)


if __name__ == "__main__":
    main()
