from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────
# Write schemas
# ──────────────────────────────────────────────

class ParkingObservationCreate(BaseModel):
    road_segment_id: str | None = Field(default=None, max_length=128)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    occupancy_rate: float = Field(..., ge=0.0, le=1.0)
    occupied_spaces: int = Field(..., ge=0)
    total_spaces: int = Field(..., ge=1)
    observed_at: datetime
    source: str = Field(..., max_length=128)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_data: dict[str, Any] | None = None


# ──────────────────────────────────────────────
# Read schemas
# ──────────────────────────────────────────────

class ParkingObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    road_segment_id: str | None
    lat: float
    lon: float
    occupancy_rate: float
    occupied_spaces: int
    total_spaces: int
    observed_at: datetime
    source: str
    confidence: float
    raw_data: dict[str, Any] | None
    created_at: datetime


# ──────────────────────────────────────────────
# Query params
# ──────────────────────────────────────────────

class ParkingQueryParams(BaseModel):
    """Optional query parameters for listing parking observations."""

    bbox: str | None = Field(
        default=None,
        description="Bounding box: min_lon,min_lat,max_lon,max_lat",
    )
    since: datetime | None = None
    until: datetime | None = None
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
