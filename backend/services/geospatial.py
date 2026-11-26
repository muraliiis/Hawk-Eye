"""
Geospatial helper functions using PostGIS / Shapely.
"""
from __future__ import annotations

from typing import Any

from geoalchemy2.functions import ST_ClosestPoint, ST_GeomFromText
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession


def bbox_to_wkt(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> str:
    """Return a WKT POLYGON string for the given bounding box (lon/lat order)."""
    return (
        f"POLYGON(("
        f"{min_lon} {min_lat}, "
        f"{max_lon} {min_lat}, "
        f"{max_lon} {max_lat}, "
        f"{min_lon} {max_lat}, "
        f"{min_lon} {min_lat}"
        f"))"
    )


def point_to_wkt(lat: float, lon: float) -> str:
    """Return a WKT POINT string from lat/lon."""
    return f"POINT({lon} {lat})"


async def segment_id_from_coords(
    lat: float, lon: float, db: AsyncSession
) -> str | None:
    """
    Return the road_segment_id of the nearest RoadSegment to the given coordinates.
    Uses ST_Distance on the segment geometry.
    Returns None when no segments exist in the database.
    """
    from models.road_segment import RoadSegment  # local import avoids circulars

    point_wkt = point_to_wkt(lat, lon)
    stmt = (
        select(RoadSegment.id)
        .where(RoadSegment.geom.isnot(None))
        .order_by(
            func.ST_Distance(
                RoadSegment.geom,
                func.ST_GeomFromText(point_wkt, 4326),
            )
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    return row  # type: ignore[return-value]


def road_event_to_geojson(events: list[Any]) -> dict[str, Any]:
    """
    Convert a list of RoadEvent ORM objects to a GeoJSON FeatureCollection.
    Works even when PostGIS geom is not loaded (falls back to lat/lon).
    """
    features: list[dict[str, Any]] = []

    for event in events:
        properties: dict[str, Any] = {
            "id": str(event.id),
            "event_type": event.event_type,
            "severity": event.severity,
            "confidence": event.confidence,
            "source": event.source,
            "road_segment_id": event.road_segment_id,
            "is_active": event.is_active,
            "verification_count": event.verification_count,
            "observed_at": event.observed_at.isoformat() if event.observed_at else None,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }

        feature: dict[str, Any] = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [event.lon, event.lat],
            },
            "properties": properties,
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def parse_bbox(bbox_str: str) -> tuple[float, float, float, float]:
    """Parse 'min_lon,min_lat,max_lon,max_lat' into a tuple of floats."""
    parts = bbox_str.split(",")
    if len(parts) != 4:
        raise ValueError(f"Invalid bbox string: {bbox_str!r}")
    min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    return min_lon, min_lat, max_lon, max_lat
