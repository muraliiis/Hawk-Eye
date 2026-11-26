from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class GPSCoord(BaseModel):
    lat: float
    lon: float
    accuracy: float = 0.0
    timestamp: datetime

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not (-90.0 <= v <= 90.0):
            raise ValueError(f"Latitude must be between -90 and 90, got {v}")
        return v

    @field_validator("lon")
    @classmethod
    def validate_lon(cls, v: float) -> float:
        if not (-180.0 <= v <= 180.0):
            raise ValueError(f"Longitude must be between -180 and 180, got {v}")
        return v


class VehicleDetection(BaseModel):
    bbox: List[float] = Field(..., min_length=4, max_length=4)
    confidence: float = Field(..., ge=0.0, le=1.0)
    class_id: int
    class_name: str
    track_id: Optional[int] = None


class DetectedPlate(BaseModel):
    plate_id: str = Field(default_factory=lambda: str(uuid4()))
    bbox: List[float] = Field(..., min_length=4, max_length=4)
    raw_text: str
    anonymized_text: str
    ocr_confidence: float = Field(..., ge=0.0, le=1.0)
    detection_confidence: float = Field(..., ge=0.0, le=1.0)
    vehicle_track_id: Optional[int] = None
    gps_coord: GPSCoord
    timestamp: datetime


class ParkingSpace(BaseModel):
    space_id: str = Field(default_factory=lambda: str(uuid4()))
    gps_coord: GPSCoord
    is_occupied: bool
    last_observed: datetime
    confidence: float = Field(..., ge=0.0, le=1.0)
    road_segment_id: str


class OccupancyReport(BaseModel):
    segment_id: str
    timestamp: datetime
    total_spaces_estimated: int = Field(..., ge=0)
    occupied_spaces: int = Field(..., ge=0)
    occupancy_rate: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)


class ParkingObservation(BaseModel):
    observation_id: str = Field(default_factory=lambda: str(uuid4()))
    gps_coord: GPSCoord
    timestamp: datetime
    parked_vehicles: List[VehicleDetection] = Field(default_factory=list)
    detected_plates: List[DetectedPlate] = Field(default_factory=list)
    occupancy_report: Optional[OccupancyReport] = None
    road_segment_id: str
    source: str = "dashcam"
