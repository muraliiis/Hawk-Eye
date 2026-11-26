"""
Unit tests for schemas and pipeline integration.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gps(**kwargs) -> dict:
    base = {"lat": 12.9716, "lon": 77.5946, "accuracy": 5.0, "timestamp": _now()}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# GPSCoord validation
# ---------------------------------------------------------------------------

class TestGPSCoordValidation:
    """GPSCoord should reject invalid latitude / longitude values."""

    def test_valid_gps_coord(self):
        """A valid GPSCoord is created without error."""
        from services.parking_anpr.schemas import GPSCoord

        coord = GPSCoord(**_gps())
        assert coord.lat == 12.9716
        assert coord.lon == 77.5946

    def test_lat_above_90_raises(self):
        """Latitude > 90 must raise a ValidationError."""
        from pydantic import ValidationError
        from services.parking_anpr.schemas import GPSCoord

        with pytest.raises(ValidationError):
            GPSCoord(**_gps(lat=91.0))

    def test_lat_below_minus_90_raises(self):
        """Latitude < -90 must raise a ValidationError."""
        from pydantic import ValidationError
        from services.parking_anpr.schemas import GPSCoord

        with pytest.raises(ValidationError):
            GPSCoord(**_gps(lat=-91.0))

    def test_lon_above_180_raises(self):
        """Longitude > 180 must raise a ValidationError."""
        from pydantic import ValidationError
        from services.parking_anpr.schemas import GPSCoord

        with pytest.raises(ValidationError):
            GPSCoord(**_gps(lon=181.0))

    def test_lon_below_minus_180_raises(self):
        """Longitude < -180 must raise a ValidationError."""
        from pydantic import ValidationError
        from services.parking_anpr.schemas import GPSCoord

        with pytest.raises(ValidationError):
            GPSCoord(**_gps(lon=-181.0))

    def test_boundary_lat_90_valid(self):
        """Latitude == 90 is exactly at the boundary and must be accepted."""
        from services.parking_anpr.schemas import GPSCoord

        coord = GPSCoord(**_gps(lat=90.0))
        assert coord.lat == 90.0

    def test_boundary_lat_minus_90_valid(self):
        """Latitude == -90 is exactly at the boundary and must be accepted."""
        from services.parking_anpr.schemas import GPSCoord

        coord = GPSCoord(**_gps(lat=-90.0))
        assert coord.lat == -90.0


# ---------------------------------------------------------------------------
# ParkingObservation schema validation
# ---------------------------------------------------------------------------

class TestParkingObservationSchema:
    """ParkingObservation should validate correctly with well-formed mock data."""

    def _make_observation(self, **overrides):
        from services.parking_anpr.schemas import (
            GPSCoord,
            OccupancyReport,
            ParkingObservation,
            VehicleDetection,
        )

        gps = GPSCoord(**_gps())

        parked = [
            VehicleDetection(
                bbox=[100.0, 200.0, 300.0, 400.0],
                confidence=0.85,
                class_id=2,
                class_name="car",
                track_id=1,
            )
        ]

        occupancy = OccupancyReport(
            segment_id="seg_001",
            timestamp=_now(),
            total_spaces_estimated=6,
            occupied_spaces=1,
            occupancy_rate=0.1667,
            confidence=0.75,
        )

        kwargs = dict(
            observation_id=str(uuid4()),
            gps_coord=gps,
            timestamp=_now(),
            parked_vehicles=parked,
            detected_plates=[],
            occupancy_report=occupancy,
            road_segment_id="seg_001",
            source="dashcam",
        )
        kwargs.update(overrides)
        return ParkingObservation(**kwargs)

    def test_valid_observation_creates_successfully(self):
        """A fully populated ParkingObservation with valid data creates without error."""
        obs = self._make_observation()
        assert obs.road_segment_id == "seg_001"
        assert obs.source == "dashcam"
        assert len(obs.parked_vehicles) == 1

    def test_observation_id_is_set(self):
        """observation_id must be non-empty."""
        obs = self._make_observation()
        assert obs.observation_id != ""

    def test_default_source_is_dashcam(self):
        """Default source value should be 'dashcam'."""
        from services.parking_anpr.schemas import GPSCoord, ParkingObservation

        gps = GPSCoord(**_gps())
        obs = ParkingObservation(
            gps_coord=gps,
            timestamp=_now(),
            road_segment_id="seg_002",
        )
        assert obs.source == "dashcam"

    def test_occupancy_report_optional(self):
        """ParkingObservation can be created with occupancy_report=None."""
        obs = self._make_observation(occupancy_report=None)
        assert obs.occupancy_report is None

    def test_parked_vehicles_defaults_to_empty_list(self):
        """When parked_vehicles is omitted it defaults to []."""
        from services.parking_anpr.schemas import GPSCoord, ParkingObservation

        gps = GPSCoord(**_gps())
        obs = ParkingObservation(
            gps_coord=gps,
            timestamp=_now(),
            road_segment_id="seg_003",
        )
        assert obs.parked_vehicles == []

    def test_vehicle_detection_bbox_length(self):
        """VehicleDetection bbox must have exactly 4 elements."""
        from pydantic import ValidationError
        from services.parking_anpr.schemas import VehicleDetection

        with pytest.raises(ValidationError):
            VehicleDetection(
                bbox=[100.0, 200.0, 300.0],  # only 3 elements — invalid
                confidence=0.8,
                class_id=2,
                class_name="car",
            )

    def test_vehicle_detection_confidence_range(self):
        """VehicleDetection confidence must be in [0, 1]."""
        from pydantic import ValidationError
        from services.parking_anpr.schemas import VehicleDetection

        with pytest.raises(ValidationError):
            VehicleDetection(
                bbox=[0.0, 0.0, 100.0, 100.0],
                confidence=1.5,  # > 1.0 — invalid
                class_id=2,
                class_name="car",
            )

    def test_occupancy_report_rate_range(self):
        """OccupancyReport occupancy_rate must be in [0, 1]."""
        from pydantic import ValidationError
        from services.parking_anpr.schemas import OccupancyReport

        with pytest.raises(ValidationError):
            OccupancyReport(
                segment_id="seg_x",
                timestamp=_now(),
                total_spaces_estimated=4,
                occupied_spaces=2,
                occupancy_rate=1.5,  # > 1.0 — invalid
                confidence=0.9,
            )
