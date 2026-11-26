from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ──────────────────────────────────────────────
# Write schemas
# ──────────────────────────────────────────────

class RoadEventCreate(BaseModel):
    event_type: str = Field(..., max_length=64, examples=["pothole"])
    severity: str = Field(..., max_length=32, examples=["high"])
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(..., max_length=128)
    road_segment_id: str | None = Field(default=None, max_length=128)
    raw_data: dict[str, Any] | None = None
    observed_at: datetime
    vehicle_speed: float | None = Field(default=None, ge=0.0)
    gps_accuracy: float | None = Field(default=None, ge=0.0)


class RoadEventUpdate(BaseModel):
    severity: str | None = Field(default=None, max_length=32)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    road_segment_id: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


# ──────────────────────────────────────────────
# Read schemas
# ──────────────────────────────────────────────

class RoadEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    severity: str
    lat: float
    lon: float
    confidence: float
    source: str
    road_segment_id: str | None
    raw_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    observed_at: datetime
    vehicle_speed: float | None
    gps_accuracy: float | None
    is_active: bool
    verification_count: int


# ──────────────────────────────────────────────
# Query / filter schemas
# ──────────────────────────────────────────────

class RoadEventFilter(BaseModel):
    """Optional query parameters for listing road events."""

    # bbox as "min_lon,min_lat,max_lon,max_lat"
    bbox: str | None = Field(
        default=None,
        description="Bounding box: min_lon,min_lat,max_lon,max_lat",
        examples=["13.38,52.51,13.42,52.53"],
    )
    event_type: str | None = None
    severity: str | None = None
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    since: datetime | None = Field(
        default=None, description="Only return events observed after this timestamp"
    )
    is_active: bool | None = True
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_bbox(self) -> "RoadEventFilter":
        if self.bbox is not None:
            parts = self.bbox.split(",")
            if len(parts) != 4:
                raise ValueError("bbox must have exactly 4 comma-separated values")
            try:
                floats = [float(p) for p in parts]
            except ValueError:
                raise ValueError("bbox values must be numeric")
            min_lon, min_lat, max_lon, max_lat = floats
            if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
                raise ValueError("bbox longitude values must be in [-180, 180]")
            if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
                raise ValueError("bbox latitude values must be in [-90, 90]")
        return self
