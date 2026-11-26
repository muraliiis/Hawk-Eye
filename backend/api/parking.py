"""
Parking API router.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2 import Geography
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.parking_observation import ParkingObservation
from schemas.parking import (
    ParkingObservationCreate,
    ParkingObservationRead,
)
from services.geospatial import bbox_to_wkt, parse_bbox

router = APIRouter()


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────

@router.post(
    "/observations",
    response_model=ParkingObservationRead,
    status_code=201,
)
async def create_parking_observation(
    payload: ParkingObservationCreate,
    db: AsyncSession = Depends(get_db),
) -> ParkingObservationRead:
    """Record a new parking occupancy observation."""
    obs = ParkingObservation(
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
    db.add(obs)
    await db.flush()
    await db.refresh(obs)
    return ParkingObservationRead.model_validate(obs)


@router.get("/observations", response_model=list[ParkingObservationRead])
async def list_parking_observations(
    bbox: str | None = Query(
        default=None, description="min_lon,min_lat,max_lon,max_lat"
    ),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[ParkingObservationRead]:
    """List parking observations with optional bbox and time filters."""
    stmt = select(ParkingObservation)

    if bbox:
        min_lon, min_lat, max_lon, max_lat = parse_bbox(bbox)
        poly_wkt = bbox_to_wkt(min_lon, min_lat, max_lon, max_lat)
        stmt = stmt.where(
            func.ST_Within(
                ParkingObservation.geom,
                func.ST_GeomFromText(poly_wkt, 4326),
            )
        )
    if since:
        stmt = stmt.where(ParkingObservation.observed_at >= since)
    if until:
        stmt = stmt.where(ParkingObservation.observed_at <= until)
    if min_confidence is not None:
        stmt = stmt.where(ParkingObservation.confidence >= min_confidence)

    stmt = stmt.order_by(ParkingObservation.observed_at.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [ParkingObservationRead.model_validate(r) for r in rows]


@router.get("/availability", response_model=list[ParkingObservationRead])
async def get_parking_availability(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    radius_meters: float = Query(500.0, ge=1.0, le=10_000.0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[ParkingObservationRead]:
    """
    Return nearby parking observations sorted by distance.
    Uses ST_DWithin for radius search, then orders by distance.
    """
    point_wkt = f"POINT({lon} {lat})"

    stmt = (
        select(ParkingObservation)
        .where(
            func.ST_DWithin(
                func.cast(ParkingObservation.geom, Geography),
                func.cast(func.ST_GeomFromText(point_wkt, 4326), Geography),
                radius_meters,
            )
        )
        .order_by(
            func.ST_Distance(
                ParkingObservation.geom,
                func.ST_GeomFromText(point_wkt, 4326),
            )
        )
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [ParkingObservationRead.model_validate(r) for r in rows]
