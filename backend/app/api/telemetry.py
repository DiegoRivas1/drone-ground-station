"""Recepción de telemetría y eventos desde la app Android."""
from fastapi import APIRouter

from app.models.schemas import FlightEventIn, TelemetryBatch
from app.services import telemetry_service
from app.services.ws_hub import hub

router = APIRouter(prefix="/api", tags=["telemetría"])


@router.post("/telemetry")
async def post_telemetry(batch: TelemetryBatch):
    saved = telemetry_service.save_batch(batch)
    if batch.samples:
        await hub.broadcast_json("telemetry", {
            "flight_id": batch.flight_id,
            "drone_model": batch.drone_model,
            "samples": [s.model_dump() for s in batch.samples],
        })
    return {"saved": saved}


@router.post("/events")
async def post_event(event: FlightEventIn):
    saved = telemetry_service.save_event(event)
    await hub.broadcast_json("event", saved)
    return saved


@router.get("/status")
def get_status():
    return telemetry_service.status()
