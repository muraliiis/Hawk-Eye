"""
models package — import all ORM models here so that SQLAlchemy's metadata
(and Alembic's autogenerate) discovers every table.
"""

from models.road_event import RoadEvent
from models.parking_observation import ParkingObservation
from models.detected_plate import DetectedPlate
from models.road_segment import RoadSegment

__all__ = [
    "RoadEvent",
    "ParkingObservation",
    "DetectedPlate",
    "RoadSegment",
]
