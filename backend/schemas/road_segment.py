from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────
# Write schemas
# ──────────────────────────────────────────────

class RoadSegmentCreate(BaseModel):
    id: str = Field(..., max_length=128, description="Unique segment ID (e.g. OSM way ID)")
    name: str = Field(..., max_length=256)
    # GeoJSON linestring coordinates [[lon, lat], ...]
    coordinates: list[list[float]] = Field(
        ...,
        min_length=2,
        description="List of [lon, lat] pairs defining the linestring",
    )
    quality_score: float = Field(default=5.0, ge=0.0, le=10.0)
    pothole_density: float = Field(default=0.0, ge=0.0)
    avg_speed: float | None = None
    speed_limit: float | None = None
    congestion_level: str = Field(default="unknown", max_length=32)


class RoadSegmentUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    quality_score: float | None = Field(default=None, ge=0.0, le=10.0)
    pothole_density: float | None = Field(default=None, ge=0.0)
    avg_speed: float | None = None
    speed_limit: float | None = None
    congestion_level: str | None = Field(default=None, max_length=32)


# ──────────────────────────────────────────────
# Read schemas
# ──────────────────────────────────────────────

class RoadSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    quality_score: float
    pothole_density: float
    avg_speed: float | None
    speed_limit: float | None
    last_updated: datetime | None
    congestion_level: str
