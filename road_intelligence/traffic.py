from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .contracts import EventCategory, GeoPoint, RoadEvent, SourceType, VehicleObservation


@dataclass(frozen=True)
class SegmentTrafficState:
    road_segment_id: str
    mean_speed_kph: float
    free_flow_speed_kph: float
    vehicle_count: int
    congestion_ratio: float
    is_congested: bool


class TrafficIntelligence:
    def summarize(self, observations: list[VehicleObservation], free_flow_speed_kph: float) -> SegmentTrafficState:
        if not observations or free_flow_speed_kph <= 0:
            raise ValueError("observations and positive free-flow speed are required")
        segment_ids = {item.road_segment_id for item in observations}
        if len(segment_ids) != 1:
            raise ValueError("summarize one road segment at a time")
        weight = sum(item.vehicle_count for item in observations)
        mean = sum(item.speed_kph * item.vehicle_count for item in observations) / weight
        ratio = max(0.0, min(1.0, 1 - mean / free_flow_speed_kph))
        return SegmentTrafficState(observations[0].road_segment_id, round(mean, 2), free_flow_speed_kph,
                                   weight, round(ratio, 3), ratio >= 0.45)

    def congestion_event(self, state: SegmentTrafficState, location: GeoPoint, observed_at: datetime) -> RoadEvent | None:
        if not state.is_congested:
            return None
        return RoadEvent(EventCategory.TRAFFIC_CONGESTION, SourceType.INFERRED, observed_at, location,
                         confidence=min(0.95, 0.5 + state.vehicle_count / 100), location_accuracy_m=25,
                         road_segment_id=state.road_segment_id,
                         attributes={"mean_speed_kph": state.mean_speed_kph, "congestion_ratio": state.congestion_ratio})
