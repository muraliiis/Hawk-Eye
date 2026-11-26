"""
Road Segments API router.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.road_event import RoadEvent
from models.road_segment import RoadSegment
from schemas.road_event import RoadEventRead
from schemas.road_segment import RoadSegmentCreate, RoadSegmentRead, RoadSegmentUpdate
from services.road_intelligence import RoadIntelligenceService

router = APIRouter()
_intelligence = RoadIntelligenceService()


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────

@router.post("/", response_model=RoadSegmentRead, status_code=201)
async def create_road_segment(
    payload: RoadSegmentCreate,
    db: AsyncSession = Depends(get_db),
) -> RoadSegmentRead:
    """Create a new road segment from a list of [lon, lat] coordinate pairs."""
    if len(payload.coordinates) < 2:
        raise HTTPException(
            status_code=422, detail="A LINESTRING requires at least 2 coordinate pairs"
        )

    shapely_line = LineString(payload.coordinates)
    geom = from_shape(shapely_line, srid=4326)

    segment = RoadSegment(
        id=payload.id,
        name=payload.name,
        geom=geom,
        quality_score=payload.quality_score,
        pothole_density=payload.pothole_density,
        avg_speed=payload.avg_speed,
        speed_limit=payload.speed_limit,
        congestion_level=payload.congestion_level,
    )
    db.add(segment)
    await db.flush()
    await db.refresh(segment)
    return RoadSegmentRead.model_validate(segment)


@router.get("/", response_model=list[RoadSegmentRead])
async def list_road_segments(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[RoadSegmentRead]:
    """List all road segments, ordered by quality score descending."""
    result = await db.execute(
        select(RoadSegment)
        .order_by(RoadSegment.quality_score.desc())
        .limit(limit)
        .offset(offset)
    )
    segments = result.scalars().all()
    return [RoadSegmentRead.model_validate(s) for s in segments]


@router.get("/{segment_id}", response_model=dict)
async def get_road_segment(
    segment_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get segment details plus aggregated road intelligence summary."""
    result = await db.execute(
        select(RoadSegment).where(RoadSegment.id == segment_id)
    )
    segment = result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=404, detail="Road segment not found")

    summary = await _intelligence.get_segment_summary(segment_id, db)
    return summary


@router.put("/{segment_id}/score", response_model=RoadSegmentRead)
async def update_segment_score(
    segment_id: str,
    update_data: RoadSegmentUpdate,
    db: AsyncSession = Depends(get_db),
) -> RoadSegmentRead:
    """Manually update quality_score and congestion_level for a segment."""
    result = await db.execute(
        select(RoadSegment).where(RoadSegment.id == segment_id)
    )
    segment = result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=404, detail="Road segment not found")

    update_fields = update_data.model_dump(exclude_none=True)
    for field, value in update_fields.items():
        setattr(segment, field, value)

    await db.flush()
    await db.refresh(segment)
    return RoadSegmentRead.model_validate(segment)


@router.get("/{segment_id}/events", response_model=list[RoadEventRead])
async def get_segment_events(
    segment_id: str,
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[RoadEventRead]:
    """List all road events associated with a specific road segment."""
    # Verify segment exists
    seg_result = await db.execute(
        select(RoadSegment.id).where(RoadSegment.id == segment_id)
    )
    if seg_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Road segment not found")

    stmt = select(RoadEvent).where(RoadEvent.road_segment_id == segment_id)
    if is_active is not None:
        stmt = stmt.where(RoadEvent.is_active == is_active)

    stmt = stmt.order_by(RoadEvent.observed_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [RoadEventRead.model_validate(e) for e in events]
