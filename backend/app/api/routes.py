"""Rutas GPS (waypoints) creadas en el panel. La app descarga la ruta ACTIVA."""
import json
import time

from fastapi import APIRouter, HTTPException

from app.database.db import connect
from app.models.schemas import RouteIn
from app.services.ws_hub import hub

router = APIRouter(prefix="/api/routes", tags=["rutas"])


def _row_to_route(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "points": json.loads(row["points_json"]),
        "created_ms": row["created_ms"],
        "active": bool(row["active"]),
    }


@router.get("")
def list_routes():
    with connect() as conn:
        return [_row_to_route(r) for r in conn.execute("SELECT * FROM routes ORDER BY created_ms DESC")]


@router.get("/active")
def active_route():
    """La que descarga el botón 'WP: CARGAR RUTA DEL PANEL' de la app. null si no hay."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM routes WHERE active = 1 LIMIT 1").fetchone()
        return _row_to_route(row) if row else None


@router.post("")
async def create_route(route: RouteIn):
    points = [p.model_dump() for p in route.points]
    for i, p in enumerate(points):
        if not p["id"] or p["id"] == "P":
            p["id"] = f"P{i + 1}"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO routes (name, points_json, created_ms) VALUES (?, ?, ?)",
            (route.name, json.dumps(points), int(time.time() * 1000)),
        )
        row = conn.execute("SELECT * FROM routes WHERE id = ?", (cur.lastrowid,)).fetchone()
    result = _row_to_route(row)
    await hub.broadcast_json("routes_changed", {"id": result["id"]})
    return result


@router.post("/{route_id}/activate")
async def activate_route(route_id: int):
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM routes WHERE id = ?", (route_id,)).fetchone():
            raise HTTPException(404, "Ruta no encontrada")
        conn.execute("UPDATE routes SET active = CASE WHEN id = ? THEN 1 ELSE 0 END", (route_id,))
    await hub.broadcast_json("routes_changed", {"id": route_id})
    return {"active": route_id}


@router.delete("/{route_id}")
async def delete_route(route_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM routes WHERE id = ?", (route_id,))
    await hub.broadcast_json("routes_changed", {"id": route_id})
    return {"deleted": route_id}
