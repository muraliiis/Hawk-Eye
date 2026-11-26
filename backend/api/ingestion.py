"""
Ingestion API router — bulk ingest of telemetry and AI frame results.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionFactory, get_db
from models.detected_plate import DetectedPlate
from models.parking_observation import ParkingObservation
from models.road_event import RoadEvent
from schemas.parking import ParkingObservationCreate
from schemas.road_event import RoadEventCreate
from services.road_intelligence import RoadIntelligenceService

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()
_intelligence = RoadIntelligenceService()


# ──────────────────────────────────────────────────────────────
# Request bodies
# ──────────────────────────────────────────────────────────────

class TelemetryPayload(BaseModel):
    road_events: list[RoadEventCreate] = Field(default_factory=list)
    parking_observations: list[ParkingObservationCreate] = Field(default_factory=list)


class DetectedPlateIngest(BaseModel):
    anonymized_text: str = Field(..., max_length=64)
    ocr_confidence: float = Field(..., ge=0.0, le=1.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    observed_at: datetime
    retention_days: int = Field(default=1, ge=1, le=7)
    parking_observation_index: int | None = Field(
        default=None,
        description="Index into the frame_result.parking_observations list this plate belongs to",
    )


class FrameResult(BaseModel):
    """AI inference result for a single camera frame."""
    road_events: list[RoadEventCreate] = Field(default_factory=list)
    parking_observations: list[ParkingObservationCreate] = Field(default_factory=list)
    detected_plates: list[DetectedPlateIngest] = Field(default_factory=list)
    frame_id: str | None = None
    captured_at: datetime | None = None


class TelemetryResponse(BaseModel):
    road_events_created: int
    parking_observations_created: int


class FrameResultResponse(BaseModel):
    road_events_created: int
    parking_observations_created: int
    plates_created: int
    frame_id: str | None


# ──────────────────────────────────────────────────────────────
# Background tasks
# ──────────────────────────────────────────────────────────────

async def _recalculate_segments(segment_ids: set[str]) -> None:
    """Recalculate quality scores for all affected segments using an independent DB session."""
    async with AsyncSessionFactory() as bg_db:
        for seg_id in segment_ids:
            try:
                await _intelligence.update_segment_score(seg_id, bg_db)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to recalculate segment %s: %s", seg_id, exc)
        await bg_db.commit()


# ──────────────────────────────────────────────────────────────
# Helper: persist a single RoadEventCreate
# ──────────────────────────────────────────────────────────────

def _build_road_event(payload: RoadEventCreate) -> RoadEvent:
    return RoadEvent(
        event_type=payload.event_type,
        severity=payload.severity,
        lat=payload.lat,
        lon=payload.lon,
        geom=func.ST_SetSRID(func.ST_MakePoint(payload.lon, payload.lat), 4326),
        confidence=payload.confidence,
        source=payload.source,
        road_segment_id=payload.road_segment_id,
        raw_data=payload.raw_data,
        observed_at=payload.observed_at,
        vehicle_speed=payload.vehicle_speed,
        gps_accuracy=payload.gps_accuracy,
    )


def _build_parking_observation(payload: ParkingObservationCreate) -> ParkingObservation:
    return ParkingObservation(
        road_segment_id=payload.road_segment_id,
        lat=payload.lat,
        lon=payload.lon,
        geom=func.ST_SetSRID(func.ST_MakePoint(payload.lon, payload.lat), 4326),
        occupancy_rate=payload.occupancy_rate,
        occupied_spaces=payload.occupied_spaces,
        total_spaces=payload.total_spaces,
        observed_at=payload.observed_at,
        source=payload.source,
        confidence=payload.confidence,
        raw_data=payload.raw_data,
    )


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────

@router.post(
    "/telemetry",
    response_model=TelemetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_telemetry(
    payload: TelemetryPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> TelemetryResponse:
    """
    Bulk ingest road events and parking observations in a single request.
    After persisting, segment quality scores are recalculated in a background task.
    """
    if len(payload.road_events) + len(payload.parking_observations) == 0:
        raise HTTPException(
            status_code=422,
            detail="Payload must contain at least one road event or parking observation",
        )

    affected_segments: set[str] = set()

    # Persist road events
    road_event_objs: list[RoadEvent] = []
    for re_payload in payload.road_events:
        event = _build_road_event(re_payload)
        db.add(event)
        road_event_objs.append(event)
        if re_payload.road_segment_id:
            affected_segments.add(re_payload.road_segment_id)

    # Persist parking observations
    parking_objs: list[ParkingObservation] = []
    for po_payload in payload.parking_observations:
        obs = _build_parking_observation(po_payload)
        db.add(obs)
        parking_objs.append(obs)

    await db.flush()

    if affected_segments:
        background_tasks.add_task(_recalculate_segments, affected_segments)

    logger.info(
        "Telemetry ingested: %d events, %d parking observations",
        len(road_event_objs),
        len(parking_objs),
    )

    return TelemetryResponse(
        road_events_created=len(road_event_objs),
        parking_observations_created=len(parking_objs),
    )


@router.post(
    "/frame-result",
    response_model=FrameResultResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_frame_result(
    payload: FrameResult,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> FrameResultResponse:
    """
    Accept a full AI inference result for a single camera frame.
    Persists road events, parking observations, and anonymised plate detections.
    """
    from datetime import timedelta

    affected_segments: set[str] = set()

    # 1. Road events
    road_event_objs: list[RoadEvent] = []
    for re_payload in payload.road_events:
        event = _build_road_event(re_payload)
        db.add(event)
        road_event_objs.append(event)
        if re_payload.road_segment_id:
            affected_segments.add(re_payload.road_segment_id)

    # 2. Parking observations — flush early so we have PKs for plate FKs
    parking_objs: list[ParkingObservation] = []
    for po_payload in payload.parking_observations:
        obs = _build_parking_observation(po_payload)
        db.add(obs)
        parking_objs.append(obs)

    await db.flush()
    # Refresh to get auto-generated IDs
    for obs in parking_objs:
        await db.refresh(obs)

    # 3. Detected plates
    plates: list[DetectedPlate] = []
    for plate_payload in payload.detected_plates:
        # Resolve parking_observation FK from index if provided
        parking_obs_id = None
        if plate_payload.parking_observation_index is not None:
            idx = plate_payload.parking_observation_index
            if 0 <= idx < len(parking_objs):
                parking_obs_id = parking_objs[idx].id

        retention_expires = plate_payload.observed_at + timedelta(
            days=plate_payload.retention_days
        )

        plate = DetectedPlate(
            anonymized_text=plate_payload.anonymized_text,
            ocr_confidence=plate_payload.ocr_confidence,
            lat=plate_payload.lat,
            lon=plate_payload.lon,
            geom=func.ST_SetSRID(
                func.ST_MakePoint(plate_payload.lon, plate_payload.lat), 4326
            ),
            observed_at=plate_payload.observed_at,
            retention_expires_at=retention_expires,
            parking_observation_id=parking_obs_id,
        )
        db.add(plate)
        plates.append(plate)

    await db.flush()

    if affected_segments:
        background_tasks.add_task(_recalculate_segments, affected_segments)

    logger.info(
        "Frame result ingested [frame=%s]: %d events, %d parking, %d plates",
        payload.frame_id,
        len(road_event_objs),
        len(parking_objs),
        len(plates),
    )

    return FrameResultResponse(
        road_events_created=len(road_event_objs),
        parking_observations_created=len(parking_objs),
        plates_created=len(plates),
        frame_id=payload.frame_id,
    )
