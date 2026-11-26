from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class RoadSegment(Base):
    __tablename__ = "road_segments"

    # Natural-key ID (e.g. OSM way ID or internal segment ref)
    id: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # Geometry: LINESTRING representing the physical road segment
    geom: Mapped[object] = mapped_column(
        Geometry("LINESTRING", srid=4326), nullable=True, index=True
    )

    # Derived quality metrics (updated by RoadIntelligenceService)
    quality_score: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    pothole_density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Speed data
    avg_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_limit: Mapped[float | None] = mapped_column(Float, nullable=True)

    # State
    last_updated: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )
    congestion_level: Mapped[str] = mapped_column(
        String(32), default="unknown", nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<RoadSegment id={self.id!r} name={self.name!r} "
            f"quality={self.quality_score:.1f} congestion={self.congestion_level!r}>"
        )
