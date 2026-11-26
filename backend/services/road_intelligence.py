"""
RoadIntelligenceService — computes quality scores and summaries for road segments.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings

settings = get_settings()

# Event types that negatively affect road quality
_NEGATIVE_EVENTS: dict[str, float] = {
    "pothole": settings.pothole_penalty,
    "road_damage": settings.road_damage_penalty,
    "crack": 0.2,
    "debris": 0.15,
    "flood": 0.4,
}

# Event types that positively affect road quality (e.g. freshly repaired)
_POSITIVE_EVENTS: dict[str, float] = {
    "repair_completed": settings.positive_observation_bonus,
    "resurfacing": settings.positive_observation_bonus,
    "clear": settings.positive_observation_bonus,
}

_CONGESTION_THRESHOLDS: list[tuple[float, str]] = [
    (0.0, "free_flow"),
    (0.3, "light"),
    (0.6, "moderate"),
    (0.8, "heavy"),
    (1.0, "stop_and_go"),
]


def _speed_to_congestion(avg_speed: float | None, speed_limit: float | None) -> str:
    """Derive a congestion label from average speed vs speed limit."""
    if avg_speed is None or speed_limit is None or speed_limit <= 0:
        return "unknown"
    ratio = avg_speed / speed_limit
    # ratio ≥ 0.8 → free_flow; < 0.2 → stop_and_go
    if ratio >= 0.8:
        return "free_flow"
    if ratio >= 0.6:
        return "light"
    if ratio >= 0.4:
        return "moderate"
    if ratio >= 0.2:
        return "heavy"
    return "stop_and_go"


class RoadIntelligenceService:
    """Service layer for road intelligence calculations."""

    # ──────────────────────────────────────────────
    # Quality score
    # ──────────────────────────────────────────────

    async def calculate_segment_quality_score(
        self, segment_id: str, db: AsyncSession
    ) -> float:
        """
        Compute a quality score (0–10) for a road segment.

        Algorithm:
          1. Start from base score (default 7.0).
          2. For each active negative event on this segment, subtract its penalty.
          3. For each active positive event, add its bonus.
          4. Clamp to [0, 10].
        """
        from models.road_event import RoadEvent  # avoid circular at module level

        stmt = (
            select(RoadEvent.event_type, func.count(RoadEvent.id).label("cnt"))
            .where(RoadEvent.road_segment_id == segment_id)
            .where(RoadEvent.is_active.is_(True))
            .group_by(RoadEvent.event_type)
        )
        result = await db.execute(stmt)
        rows = result.all()

        score = settings.base_quality_score
        for event_type, count in rows:
            et = event_type.lower()
            if et in _NEGATIVE_EVENTS:
                score -= _NEGATIVE_EVENTS[et] * count
            elif et in _POSITIVE_EVENTS:
                score += _POSITIVE_EVENTS[et] * count

        return round(max(0.0, min(10.0, score)), 2)

    # ──────────────────────────────────────────────
    # Segment summary
    # ──────────────────────────────────────────────

    async def get_segment_summary(
        self, segment_id: str, db: AsyncSession
    ) -> dict[str, Any]:
        """
        Return a dict with:
          - quality_score
          - event_counts_by_type
          - congestion_level
          - avg_speed
        """
        from models.road_event import RoadEvent
        from models.road_segment import RoadSegment

        # 1. Load segment
        segment_result = await db.execute(
            select(RoadSegment).where(RoadSegment.id == segment_id)
        )
        segment = segment_result.scalar_one_or_none()

        if segment is None:
            return {
                "segment_id": segment_id,
                "error": "segment_not_found",
            }

        # 2. Event counts by type
        counts_result = await db.execute(
            select(RoadEvent.event_type, func.count(RoadEvent.id).label("cnt"))
            .where(RoadEvent.road_segment_id == segment_id)
            .where(RoadEvent.is_active.is_(True))
            .group_by(RoadEvent.event_type)
        )
        event_counts: dict[str, int] = {
            row.event_type: row.cnt for row in counts_result.all()
        }

        # 3. Recalculate quality score
        quality_score = await self.calculate_segment_quality_score(segment_id, db)

        # 4. Derive congestion from segment data
        congestion = segment.congestion_level
        if congestion == "unknown":
            congestion = _speed_to_congestion(segment.avg_speed, segment.speed_limit)

        return {
            "segment_id": segment_id,
            "name": segment.name,
            "quality_score": quality_score,
            "event_counts_by_type": event_counts,
            "congestion_level": congestion,
            "avg_speed": segment.avg_speed,
            "speed_limit": segment.speed_limit,
            "pothole_density": segment.pothole_density,
        }

    # ──────────────────────────────────────────────
    # Persist recalculated score back to DB
    # ──────────────────────────────────────────────

    async def update_segment_score(
        self, segment_id: str, db: AsyncSession
    ) -> None:
        """Recalculate and persist quality_score + congestion_level for segment."""
        from models.road_segment import RoadSegment
        from sqlalchemy import update

        score = await self.calculate_segment_quality_score(segment_id, db)

        await db.execute(
            update(RoadSegment)
            .where(RoadSegment.id == segment_id)
            .values(quality_score=score)
        )
        await db.flush()
