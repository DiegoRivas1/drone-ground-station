"""Modelos de datos (Pydantic) que intercambian la app Android y el panel."""
from typing import Optional

from pydantic import BaseModel, Field


class TelemetrySample(BaseModel):
    timestamp_ms: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    velocity_x: Optional[float] = None   # Norte m/s
    velocity_y: Optional[float] = None   # Este m/s
    velocity_z: Optional[float] = None   # Abajo m/s
    speed_mps: Optional[float] = None
    heading_deg: Optional[float] = None
    battery_pct: Optional[int] = None
    is_flying: bool = False
    motors_on: bool = False
    satellites: Optional[int] = None
    gps_level: Optional[int] = None
    flight_mode: Optional[str] = None


class TelemetryBatch(BaseModel):
    flight_id: str = Field(min_length=1, max_length=100)
    drone_model: Optional[str] = None
    samples: list[TelemetrySample]


class FlightEventIn(BaseModel):
    flight_id: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=60)
    details: str = ""
    timestamp_ms: int
    telemetry: Optional[TelemetrySample] = None


class RoutePointIn(BaseModel):
    id: str = Field(default="P", max_length=20)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude_m: float = Field(ge=1.5, le=30)
    speed_mps: float = Field(default=1.0, gt=0, le=5)


class RouteIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    points: list[RoutePointIn] = Field(min_length=2, max_length=99)


class VideoComplete(BaseModel):
    chunks: int = 0
    incomplete: bool = False
