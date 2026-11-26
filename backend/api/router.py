"""
Main APIRouter — aggregates all sub-routers.
"""
from fastapi import APIRouter

from api.road_events import router as road_events_router
from api.parking import router as parking_router
from api.road_segments import router as road_segments_router
from api.ingestion import router as ingestion_router
from api.health import router as health_router

api_router = APIRouter()

api_router.include_router(road_events_router, prefix="/events", tags=["Road Events"])
api_router.include_router(parking_router, prefix="/parking", tags=["Parking"])
api_router.include_router(road_segments_router, prefix="/segments", tags=["Road Segments"])
api_router.include_router(ingestion_router, prefix="/ingest", tags=["Ingestion"])
api_router.include_router(health_router, prefix="/health", tags=["Health"])
