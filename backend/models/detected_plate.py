import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class DetectedPlate(Base):
    __tablename__ = "detected_plates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )

    # Anonymised plate text (e.g. hashed / partial)
    anonymized_text: Mapped[str] = mapped_column(String(64), nullable=False)
    ocr_confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Location at time of detection
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[object] = mapped_column(
        Geometry("POINT", srid=4326), nullable=True, index=True
    )

    # Timestamps
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    retention_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # GDPR-style purge flag
    is_purged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # FK → parking observation this detection is associated with
    parking_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parking_observations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    parking_observation: Mapped["ParkingObservation"] = relationship(  # type: ignore[name-defined]
        "ParkingObservation",
        back_populates=None,
        lazy="select",
        foreign_keys=[parking_observation_id],
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<DetectedPlate id={self.id} purged={self.is_purged} "
            f"expires={self.retention_expires_at}>"
        )
