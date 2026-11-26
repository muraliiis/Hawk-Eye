"""
Road Events API router.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from geoalchemy2 import Geography
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionFactory, get_db
from models.road_event import RoadEvent
from schemas.road_event import RoadEventCreate, RoadEventFilter, RoadEventRead
from services.geospatial import bbox_to_wkt, parse_bbox, segment_id_from_coords

router = APIRouter()


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _make_point_wkt(lat: float, lon: float) -> str:
    return f"POINT({lon} {lat})"


async def _auto_assign_segment(event_id: uuid.UUID, lat: float, lon: float) -> None:
    """Background: assign road_segment_id using an independent DB session."""
    async with AsyncSessionFactory() as bg_db:
        seg_id = await segment_id_from_coords(lat, lon, bg_db)
        if seg_id:
            await bg_db.execute(
                update(RoadEvent)
                .where(RoadEvent.id == event_id)
                .values(road_segment_id=seg_id)
            )
            await bg_db.commit()


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────

@router.post("/", response_model=RoadEventRead, status_code=status.HTTP_201_CREATED)
async def create_road_event(
    payload: RoadEventCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> RoadEventRead:
    """Create a new road event. PostGIS geometry is derived from lat/lon."""
    point_wkt = _make_point_wkt(payload.lat, payload.lon)

    event = RoadEvent(
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
    db.add(event)
    await db.flush()
    await db.refresh(event)

    if event.road_segment_id is None:
        background_tasks.add_task(_auto_assign_segment, event.id, event.lat, event.lon)

    return RoadEventRead.model_validate(event)


@router.get("/nearby", response_model=list[RoadEventRead])
async def get_nearby_events(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Centre latitude"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Centre longitude"),
    radius_meters: float = Query(500.0, ge=1.0, le=50_000.0, description="Search radius in metres"),
    event_type: str | None = Query(default=None),
    is_active: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[RoadEventRead]:
    """Return road events within *radius_meters* of the given lat/lon (uses ST_DWithin)."""
    point_wkt = _make_point_wkt(lat, lon)

    stmt = (
        select(RoadEvent)
        .where(
            func.ST_DWithin(
                func.cast(RoadEvent.geom, Geography),
                func.cast(func.ST_GeomFromText(point_wkt, 4326), Geography),
                radius_meters,
            )
        )
        .where(RoadEvent.is_active == is_active)
    )

    if event_type:
        stmt = stmt.where(RoadEvent.event_type == event_type)

    stmt = stmt.order_by(
        func.ST_Distance(
            RoadEvent.geom,
            func.ST_GeomFromText(point_wkt, 4326),
        )
    ).limit(limit)

    result = await db.execute(stmt)
    events = result.scalars().all()
    return [RoadEventRead.model_validate(e) for e in events]


@router.get("/", response_model=list[RoadEventRead])
async def list_road_events(
    event_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    since: datetime | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    bbox: str | None = Query(
        default=None,
        description="min_lon,min_lat,max_lon,max_lat",
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[RoadEventRead]:
    """List road events with optional filters."""
    stmt = select(RoadEvent)

    if is_active is not None:
        stmt = stmt.where(RoadEvent.is_active == is_active)
    if event_type:
        stmt = stmt.where(RoadEvent.event_type == event_type)
    if severity:
        stmt = stmt.where(RoadEvent.severity == severity)
    if min_confidence is not None:
        stmt = stmt.where(RoadEvent.confidence >= min_confidence)
    if since:
        stmt = stmt.where(RoadEvent.observed_at >= since)
    if bbox:
        min_lon, min_lat, max_lon, max_lat = parse_bbox(bbox)
        poly_wkt = bbox_to_wkt(min_lon, min_lat, max_lon, max_lat)
        stmt = stmt.where(
            func.ST_Within(
                RoadEvent.geom,
                func.ST_GeomFromText(poly_wkt, 4326),
            )
        )

    stmt = (
        stmt.order_by(RoadEvent.observed_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    events = result.scalars().all()
    return [RoadEventRead.model_validate(e) for e in events]


@router.get("/{event_id}", response_model=RoadEventRead)
async def get_road_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RoadEventRead:
    """Retrieve a single road event by ID."""
    result = await db.execute(select(RoadEvent).where(RoadEvent.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Road event not found")
    return RoadEventRead.model_validate(event)


@router.put("/{event_id}/verify", response_model=RoadEventRead)
async def verify_road_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RoadEventRead:
    """Increment the verification count for an event (crowd-sourced verification)."""
    result = await db.execute(select(RoadEvent).where(RoadEvent.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Road event not found")

    event.verification_count += 1
    await db.flush()
    await db.refresh(event)
    return RoadEventRead.model_validate(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_road_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a road event by setting is_active=False."""
    result = await db.execute(select(RoadEvent).where(RoadEvent.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Road event not found")

    event.is_active = False
    await db.flush()
