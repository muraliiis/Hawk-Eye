import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ParkingObservation(Base):
    __tablename__ = "parking_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )

    road_segment_id: Mapped[str] = mapped_column(
        String(128), nullable=True, index=True
    )

    # Location
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[object] = mapped_column(
        Geometry("POINT", srid=4326), nullable=True, index=True
    )

    # Occupancy
    occupancy_rate: Mapped[float] = mapped_column(Float, nullable=False)
    occupied_spaces: Mapped[int] = mapped_column(Integer, nullable=False)
    total_spaces: Mapped[int] = mapped_column(Integer, nullable=False)

    # Metadata
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ParkingObservation id={self.id} segment={self.road_segment_id} "
            f"occupancy={self.occupancy_rate:.2%}>"
        )
