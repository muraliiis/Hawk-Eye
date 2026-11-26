from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from .contracts import GeoPoint


@dataclass(frozen=True)
class GnssSample:
    timestamp: datetime
    location: GeoPoint
    accuracy_m: float
    speed_kph: float
    heading_deg: float | None = None


@dataclass(frozen=True)
class ImuSample:
    timestamp: datetime
    longitudinal_accel_mps2: float
    vertical_accel_mps2: float
    yaw_rate_dps: float


@dataclass(frozen=True)
class LocationEstimate:
    location: GeoPoint
    accuracy_m: float
    speed_kph: float
    age_ms: float
    road_segment_id: str | None = None


def distance_m(a: GeoPoint, b: GeoPoint) -> float:
    radius = 6_371_000
    d_lat, d_lon = radians(b.latitude - a.latitude), radians(b.longitude - a.longitude)
    h = sin(d_lat / 2) ** 2 + cos(radians(a.latitude)) * cos(radians(b.latitude)) * sin(d_lon / 2) ** 2
    return 2 * radius * asin(sqrt(h))


class SensorFusion:
    def __init__(self, samples: list[GnssSample], max_alignment_ms: int = 750) -> None:
        if not samples:
            raise ValueError("at least one GNSS sample is required")
        self.samples = sorted(samples, key=lambda item: item.timestamp)
        self.max_alignment_ms = max_alignment_ms

    def locate(self, frame_time: datetime, candidate_segments: dict[str, GeoPoint] | None = None) -> LocationEstimate:
        times = [sample.timestamp for sample in self.samples]
        index = bisect_left(times, frame_time)
        nearby = self.samples[max(0, index - 1):min(len(self.samples), index + 1)]
        sample = min(nearby, key=lambda item: abs((item.timestamp - frame_time).total_seconds()))
        age_ms = abs((sample.timestamp - frame_time).total_seconds()) * 1000
        if age_ms > self.max_alignment_ms:
            raise ValueError(f"GNSS sample is stale ({age_ms:.0f}ms)")
        segment_id = None
        if candidate_segments:
            segment_id, snapped = min(candidate_segments.items(), key=lambda item: distance_m(sample.location, item[1]))
            snap_distance = distance_m(sample.location, snapped)
            if snap_distance > max(30.0, sample.accuracy_m * 3):
                segment_id = None
            else:
                return LocationEstimate(snapped, sample.accuracy_m + snap_distance, sample.speed_kph, age_ms, segment_id)
        return LocationEstimate(sample.location, sample.accuracy_m, sample.speed_kph, age_ms, segment_id)

    @staticmethod
    def harsh_braking(imu: ImuSample, threshold_mps2: float = -3.0) -> bool:
        return imu.longitudinal_accel_mps2 <= threshold_mps2
