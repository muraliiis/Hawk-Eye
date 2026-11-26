"""
Health check endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.redis_cache import redis_cache

router = APIRouter()


@router.get("/", summary="Health check")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """
    Returns service health status.
    Performs a lightweight connectivity check against PostgreSQL and Redis.
    """
    # PostgreSQL connectivity
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_status = f"error: {exc}"

    # Redis connectivity
    redis_status = "connected"
    try:
        ok = await redis_cache.ping()
        if not ok:
            redis_status = "unreachable"
    except Exception as exc:  # noqa: BLE001
        redis_status = f"error: {exc}"

    overall = "ok" if db_status == "connected" and redis_status == "connected" else "degraded"

    return {
        "status": overall,
        "db": db_status,
        "redis": redis_status,
    }
