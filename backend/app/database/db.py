"""SQLite: vuelos, telemetría, eventos, rutas y videos.

Se abre una conexión por operación (SQLite en modo WAL lo soporta bien y evita
problemas de hilos con FastAPI).
"""
import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS flights (
    id            TEXT PRIMARY KEY,
    drone_model   TEXT,
    started_at_ms INTEGER NOT NULL,
    last_seen_ms  INTEGER NOT NULL,
    samples       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS telemetry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id   TEXT NOT NULL,
    ts_ms       INTEGER NOT NULL,
    latitude    REAL,
    longitude   REAL,
    altitude_m  REAL,
    velocity_x  REAL,
    velocity_y  REAL,
    velocity_z  REAL,
    speed_mps   REAL,
    heading_deg REAL,
    battery_pct INTEGER,
    is_flying   INTEGER,
    motors_on   INTEGER,
    satellites  INTEGER,
    gps_level   INTEGER,
    flight_mode TEXT
);
CREATE INDEX IF NOT EXISTS idx_telemetry_flight ON telemetry(flight_id, ts_ms);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id   TEXT NOT NULL,
    ts_ms       INTEGER NOT NULL,
    type        TEXT NOT NULL,
    details     TEXT,
    latitude    REAL,
    longitude   REAL,
    altitude_m  REAL,
    battery_pct INTEGER
);
CREATE INDEX IF NOT EXISTS idx_events_flight ON events(flight_id, ts_ms);

CREATE TABLE IF NOT EXISTS routes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    points_json TEXT NOT NULL,
    created_ms  INTEGER NOT NULL,
    active      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS videos (
    id          TEXT PRIMARY KEY,
    flight_id   TEXT,
    filename    TEXT NOT NULL,
    bytes       INTEGER NOT NULL DEFAULT 0,
    chunks      INTEGER NOT NULL DEFAULT 0,
    last_seq    INTEGER NOT NULL DEFAULT -1,
    started_ms  INTEGER NOT NULL,
    updated_ms  INTEGER NOT NULL,
    completed   INTEGER NOT NULL DEFAULT 0,
    incomplete  INTEGER NOT NULL DEFAULT 0
);
"""


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]
