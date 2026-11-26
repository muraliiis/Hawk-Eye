from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .contracts import EventCategory, GeoPoint, RoadEvent, SourceType


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    frame_timestamp: datetime
    bbox_area_ratio: float = 0.02
    model_version: str = "unknown"


class PerceptionNormalizer:
    """Validates model output; geographic placement stays in Sensor Fusion."""

    LABELS = {
        "pothole": EventCategory.POTHOLE, "crack": EventCategory.CRACK,
        "uneven_surface": EventCategory.UNEVEN_SURFACE, "speed_breaker": EventCategory.SPEED_BREAKER,
        "obstacle": EventCategory.OBSTACLE, "waterlogging": EventCategory.WATERLOGGING,
        "construction": EventCategory.CONSTRUCTION, "road_closure": EventCategory.ROAD_CLOSURE,
        "speed_limit_sign": EventCategory.SPEED_LIMIT_SIGN,
    }

    def normalize(self, detection: Detection, location: GeoPoint, accuracy_m: float,
                  road_segment_id: str | None = None) -> RoadEvent | None:
        category = self.LABELS.get(detection.label)
        if category is None or not 0 <= detection.confidence <= 1 or detection.confidence < 0.45:
            return None
        # Tiny detections are less trustworthy; this is an explicit, replaceable calibration policy.
        calibrated = detection.confidence * min(1.0, 0.5 + detection.bbox_area_ratio * 10)
        return RoadEvent(category=category, source_type=SourceType.CAMERA_OBSERVED,
                         observed_at=detection.frame_timestamp, location=location,
                         location_accuracy_m=accuracy_m, confidence=round(calibrated, 3),
                         road_segment_id=road_segment_id,
                         attributes={"model_version": detection.model_version, "raw_label": detection.label})
