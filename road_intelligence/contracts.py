from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class StringEnum(str, Enum):
    """Python 3.10-compatible equivalent of enum.StrEnum."""


class EventCategory(StringEnum):
    POTHOLE = "pothole"
    CRACK = "crack"
    UNEVEN_SURFACE = "uneven_surface"
    SPEED_BREAKER = "speed_breaker"
    OBSTACLE = "obstacle"
    WATERLOGGING = "waterlogging"
    CONSTRUCTION = "construction"
    ROAD_CLOSURE = "road_closure"
    TRAFFIC_CONGESTION = "traffic_congestion"
    INCIDENT = "incident"
    SPEED_LIMIT_SIGN = "speed_limit_sign"


class SourceType(StringEnum):
    CAMERA_OBSERVED = "camera_observed"
    SENSOR_OBSERVED = "sensor_observed"
    TELEMETRY_AGGREGATED = "telemetry_aggregated"
    EXTERNAL_PROVIDER = "external_provider"
    INFERRED = "inferred"


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("location must be valid WGS-84 coordinates")


@dataclass(frozen=True)
class RoadEvent:
    category: EventCategory
    source_type: SourceType
    observed_at: datetime
    location: GeoPoint
    confidence: float
    location_accuracy_m: float
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex}")
    road_segment_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between zero and one")
        if self.location_accuracy_m < 0:
            raise ValueError("location_accuracy_m cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["category"] = self.category.value
        payload["source_type"] = self.source_type.value
        payload["observed_at"] = self.observed_at.astimezone(timezone.utc).isoformat()
        return payload


@dataclass(frozen=True)
class VehicleObservation:
    road_segment_id: str
    observed_at: datetime
    speed_kph: float
    vehicle_count: int = 1
    source_type: SourceType = SourceType.TELEMETRY_AGGREGATED

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.speed_kph < 0 or self.vehicle_count < 1:
            raise ValueError("invalid traffic observation")
