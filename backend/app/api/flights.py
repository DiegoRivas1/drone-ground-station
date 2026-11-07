"""Consulta de vuelos guardados."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.services import telemetry_service

router = APIRouter(prefix="/api/flights", tags=["vuelos"])


@router.get("")
def list_flights():
    return telemetry_service.list_flights()


@router.get("/{flight_id}")
def get_flight(flight_id: str):
    flight = telemetry_service.get_flight(flight_id)
    if not flight:
        raise HTTPException(404, "Vuelo no encontrado")
    return flight


@router.get("/{flight_id}/telemetry")
def get_telemetry(flight_id: str, limit: int = 5000, since_ms: int | None = None):
    return telemetry_service.get_telemetry(flight_id, min(max(limit, 1), 50000), since_ms)


@router.get("/{flight_id}/events")
def get_events(flight_id: str):
    return telemetry_service.get_events(flight_id)


@router.get("/{flight_id}/export.csv", response_class=PlainTextResponse)
def export_csv(flight_id: str):
    if not telemetry_service.get_flight(flight_id):
        raise HTTPException(404, "Vuelo no encontrado")
    return PlainTextResponse(
        telemetry_service.export_csv(flight_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{flight_id}.csv"'},
    )
