"""Almacenamiento y consulta de vuelos, telemetría y eventos."""
import csv
import io
import time

from app.database.db import connect, rows_to_dicts
from app.models.schemas import FlightEventIn, TelemetryBatch, TelemetrySample

TELEMETRY_COLUMNS = [
    "latitude", "longitude", "altitude_m", "velocity_x", "velocity_y", "velocity_z",
    "speed_mps", "heading_deg", "battery_pct", "is_flying", "motors_on",
    "satellites", "gps_level", "flight_mode",
]

# Última telemetría recibida (para el estado del panel), en memoria.
latest: dict = {"flight_id": None, "received_ms": None, "sample": None}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _upsert_flight(conn, flight_id: str, drone_model: str | None, ts_ms: int, add_samples: int = 0) -> None:
    conn.execute(
        """
        INSERT INTO flights (id, drone_model, started_at_ms, last_seen_ms, samples)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            drone_model = COALESCE(excluded.drone_model, flights.drone_model),
            last_seen_ms = MAX(flights.last_seen_ms, excluded.last_seen_ms),
            samples = flights.samples + ?
        """,
        (flight_id, drone_model, ts_ms, ts_ms, add_samples, add_samples),
    )


def save_batch(batch: TelemetryBatch) -> int:
    if not batch.samples:
        return 0
    rows = []
    for s in batch.samples:
        rows.append(
            (batch.flight_id, s.timestamp_ms, s.latitude, s.longitude, s.altitude_m,
             s.velocity_x, s.velocity_y, s.velocity_z, s.speed_mps, s.heading_deg,
             s.battery_pct, int(s.is_flying), int(s.motors_on), s.satellites,
             s.gps_level, s.flight_mode)
        )
    with connect() as conn:
        _upsert_flight(conn, batch.flight_id, batch.drone_model,
                       batch.samples[0].timestamp_ms, len(rows))
        conn.execute("UPDATE flights SET last_seen_ms = MAX(last_seen_ms, ?) WHERE id = ?",
                     (batch.samples[-1].timestamp_ms, batch.flight_id))
        conn.executemany(
            f"""INSERT INTO telemetry (flight_id, ts_ms, {", ".join(TELEMETRY_COLUMNS)})
                VALUES (?, ?, {", ".join("?" for _ in TELEMETRY_COLUMNS)})""",
            rows,
        )
    last = batch.samples[-1]
    latest.update(flight_id=batch.flight_id, received_ms=_now_ms(),
                  sample=last.model_dump(), drone_model=batch.drone_model)
    return len(rows)


def save_event(e: FlightEventIn) -> dict:
    t: TelemetrySample | None = e.telemetry
    with connect() as conn:
        _upsert_flight(conn, e.flight_id, None, e.timestamp_ms)
        cur = conn.execute(
            """INSERT INTO events (flight_id, ts_ms, type, details, latitude, longitude, altitude_m, battery_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (e.flight_id, e.timestamp_ms, e.type, e.details,
             t.latitude if t else None, t.longitude if t else None,
             t.altitude_m if t else None, t.battery_pct if t else None),
        )
        event_id = cur.lastrowid
    return {
        "id": event_id, "flight_id": e.flight_id, "ts_ms": e.timestamp_ms,
        "type": e.type, "details": e.details,
        "latitude": t.latitude if t else None, "longitude": t.longitude if t else None,
    }


def list_flights() -> list[dict]:
    with connect() as conn:
        return rows_to_dicts(conn.execute(
            """SELECT f.*, (SELECT COUNT(*) FROM events e WHERE e.flight_id = f.id) AS events
               FROM flights f ORDER BY last_seen_ms DESC"""))


def get_flight(flight_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM flights WHERE id = ?", (flight_id,)).fetchone()
        return dict(row) if row else None


def get_telemetry(flight_id: str, limit: int = 5000, since_ms: int | None = None) -> list[dict]:
    with connect() as conn:
        if since_ms is not None:
            rows = conn.execute(
                "SELECT * FROM telemetry WHERE flight_id = ? AND ts_ms > ? ORDER BY ts_ms LIMIT ?",
                (flight_id, since_ms, limit))
        else:
            # Las últimas `limit` muestras, en orden cronológico.
            rows = conn.execute(
                """SELECT * FROM (SELECT * FROM telemetry WHERE flight_id = ? ORDER BY ts_ms DESC LIMIT ?)
                   ORDER BY ts_ms""", (flight_id, limit))
        return rows_to_dicts(rows)


def get_events(flight_id: str) -> list[dict]:
    with connect() as conn:
        return rows_to_dicts(conn.execute(
            "SELECT * FROM events WHERE flight_id = ? ORDER BY ts_ms", (flight_id,)))


def export_csv(flight_id: str) -> str:
    """Mismo formato de columnas que el CSV del teléfono + campos extra."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["timestamp_ms", "event", *TELEMETRY_COLUMNS, "details"])
    lines = []
    with connect() as conn:
        for r in conn.execute("SELECT * FROM telemetry WHERE flight_id = ?", (flight_id,)):
            lines.append([r["ts_ms"], "TELEMETRY", *[r[c] for c in TELEMETRY_COLUMNS], ""])
        for r in conn.execute("SELECT * FROM events WHERE flight_id = ?", (flight_id,)):
            row = {c: None for c in TELEMETRY_COLUMNS}
            row.update(latitude=r["latitude"], longitude=r["longitude"],
                       altitude_m=r["altitude_m"], battery_pct=r["battery_pct"])
            lines.append([r["ts_ms"], r["type"], *[row[c] for c in TELEMETRY_COLUMNS], r["details"]])
    lines.sort(key=lambda x: x[0])  # telemetría y eventos intercalados por tiempo
    w.writerows(lines)
    return out.getvalue()


def status() -> dict:
    age = None
    if latest["received_ms"]:
        age = _now_ms() - latest["received_ms"]
    return {**latest, "age_ms": age, "server_time_ms": _now_ms()}
