from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import logging
from pathlib import Path
import socket
from typing import Any, Literal
from urllib.parse import urlparse
import urllib.request

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from road_intelligence.contracts import GeoPoint
from road_intelligence.sensor_fusion import GnssSample, ImuSample

try:
    from .frame_inference import MODEL_VERSION, infer_dashcam_frame
    from .store import store
except ImportError:  # pragma: no cover - when launched directly inside backend/
    from frame_inference import MODEL_VERSION, infer_dashcam_frame
    from store import store

logger = logging.getLogger(__name__)

try:
    try:
        from .api.router import api_router as v1_api_router
        from .database import create_tables
    except ImportError:
        from api.router import api_router as v1_api_router
        from database import create_tables
except Exception as exc:  # pragma: no cover - optional DB dependencies
    logger.warning("Optional PostgreSQL/PostGIS v1 router disabled (%s)", exc)
    v1_api_router = None
    create_tables = None


@asynccontextmanager
async def lifespan(app_: FastAPI):
    if create_tables is not None:
        try:
            await create_tables()
        except Exception as exc:  # pragma: no cover - graceful fallback without Postgres
            logger.warning("Skipping DB table init (Postgres unavailable): %s", exc)
    yield


app = FastAPI(
    title="Road Intelligence Platform API",
    version="1.0.0",
    description="FastAPI bridge exposing deterministic road_intelligence services and live UI state.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if v1_api_router is not None:
    app.include_router(v1_api_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Curated Public Internet Dashcam Feeds (proxied/cached for same-origin Canvas)
# ---------------------------------------------------------------------------

FEED_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "feeds"
MAX_FEED_BYTES = 40 * 1024 * 1024

DASHCAM_FEEDS: list[dict[str, str]] = [
    {
        "feed_id": "road_defects_feed",
        "title": "Road Damage Dashcam (Internet Feed #1)",
        "source_label": "Public GitHub Road-Damage Sample (MP4)",
        "url": "https://raw.githubusercontent.com/Tanvir-Pandit/Road-Damage-with-YOLOv8/main/videos/crack%202.mp4",
        "default_segment_id": "osm-way-richmond-shanthi",
    },
    {
        "feed_id": "urban_cracks_feed",
        "title": "Urban Asphalt Cracks (Internet Feed #2)",
        "source_label": "Public GitHub Road-Damage Sample #2 (MP4)",
        "url": "https://raw.githubusercontent.com/Tanvir-Pandit/Road-Damage-with-YOLOv8/main/videos/crack.mp4",
        "default_segment_id": "osm-way-shanthi-ejipura",
    },
]


def _validate_public_http_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Stream URL must be a valid public http(s) URL")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError("Private or loopback stream URLs are blocked")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve stream host '{host}'") from exc
    for info in infos:
        ip_str = info[4][0]
        ip_obj = ipaddress.ip_address(ip_str)
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        ):
            raise ValueError("Private or internal IP addresses are not permitted for stream URLs")
    return parsed.geturl()


def _download_or_get_cached_feed(url: str) -> Path:
    FEED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    dest = FEED_CACHE_DIR / f"{digest}.mp4"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest

    tmp = FEED_CACHE_DIR / f"{digest}.tmp"
    req = urllib.request.Request(url, headers={"User-Agent": "RoadSense-Dashcam/1.0"})
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=25) as resp, tmp.open("wb") as out:
            while True:
                chunk = resp.read(131072)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FEED_BYTES:
                    raise ValueError("Remote video feed exceeds 40 MB size limit")
                out.write(chunk)
        if total == 0:
            raise ValueError("Remote video feed returned empty response")
        tmp.replace(dest)
        return dest
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


class GnssSampleIn(BaseModel):
    timestamp: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_m: float = Field(..., ge=0)
    speed_kph: float = Field(..., ge=0)
    heading_deg: float | None = None


class ImuSampleIn(BaseModel):
    timestamp: datetime
    longitudinal_accel_mps2: float
    vertical_accel_mps2: float
    yaw_rate_dps: float


class PerceptionIngestIn(BaseModel):
    label: str
    confidence: float
    frame_timestamp: datetime
    bbox_area_ratio: float = Field(default=0.04, ge=0.0, le=1.0)
    model_version: str = MODEL_VERSION
    gnss_samples: list[GnssSampleIn] = Field(..., min_length=1)
    imu_sample: ImuSampleIn | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class DriverFeedbackIn(BaseModel):
    action: Literal["confirm", "cleared"]


class AdminEventModerationIn(BaseModel):
    workflow_status: Literal["active", "verified", "resolved", "dismissed"]
    severity: Literal["low", "medium", "high"] | None = None


class RouteCompareIn(BaseModel):
    origin: str
    destination: str


class SpeedAdvisoryIn(BaseModel):
    legal_speed_limit_kph: int | None = None
    hazard: str | None = None
    distance_to_hazard_m: float | None = None


class AdminSegmentUpdateIn(BaseModel):
    closed: bool | None = None
    extra_hazard_penalty: float | None = None
    mean_speed_kph: float | None = Field(default=None, ge=0)
    vehicle_count: int = Field(default=12, ge=1)


_replay_last_published: dict[tuple[str, str], datetime] = {}
REPLAY_EVENT_DEDUP_SECONDS = 15


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "schema_version": "1.0",
        "event_count": len(store.events),
        "segment_count": len(store.segments),
        "fleet_count": len(store.fleet),
    }


@app.get("/api/network")
def get_network() -> dict[str, Any]:
    return store.list_network()


@app.get("/api/events")
def list_events(
    category: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    segment_id: str | None = Query(default=None),
) -> dict[str, Any]:
    items = store.list_events(
        category=category,
        source_type=source_type,
        status=status,
        min_confidence=min_confidence,
        segment_id=segment_id,
    )
    return {"events": items, "count": len(items)}


@app.get("/api/dashcam/feeds")
def list_dashcam_feeds() -> dict[str, Any]:
    return {"feeds": DASHCAM_FEEDS}


@app.get("/api/dashcam/stream")
async def stream_dashcam_feed(
    feed_id: str | None = Query(default=None),
    url: str | None = Query(default=None),
) -> FileResponse:
    target_url: str | None = None
    if feed_id:
        match = next((f for f in DASHCAM_FEEDS if f["feed_id"] == feed_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"unknown dashcam feed '{feed_id}'")
        target_url = match["url"]
    elif url:
        try:
            target_url = _validate_public_http_url(url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        target_url = DASHCAM_FEEDS[0]["url"]

    try:
        video_path = await asyncio.to_thread(_download_or_get_cached_feed, target_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to fetch remote feed: {exc}") from exc

    return FileResponse(path=video_path, media_type="video/mp4", filename=video_path.name)


@app.post("/api/perception/ingest")
def ingest_perception(body: PerceptionIngestIn) -> dict[str, Any]:
    gnss = [
        GnssSample(
            timestamp=_ensure_tz(s.timestamp),
            location=GeoPoint(s.latitude, s.longitude),
            accuracy_m=s.accuracy_m,
            speed_kph=s.speed_kph,
            heading_deg=s.heading_deg,
        )
        for s in body.gnss_samples
    ]
    imu = None
    if body.imu_sample is not None:
        imu = ImuSample(
            timestamp=_ensure_tz(body.imu_sample.timestamp),
            longitudinal_accel_mps2=body.imu_sample.longitudinal_accel_mps2,
            vertical_accel_mps2=body.imu_sample.vertical_accel_mps2,
            yaw_rate_dps=body.imu_sample.yaw_rate_dps,
        )

    try:
        return store.ingest_perception(
            label=body.label,
            confidence=body.confidence,
            bbox_area_ratio=body.bbox_area_ratio,
            model_version=body.model_version,
            frame_timestamp=_ensure_tz(body.frame_timestamp),
            gnss_samples=gnss,
            imu_sample=imu,
            attributes=body.attributes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/perception/replay-frame")
async def analyze_replay_frame(
    frame: UploadFile = File(...),
    road_segment_id: str = Form(...),
    frame_timestamp: datetime = Form(...),
    speed_kph: float = Form(default=30.0),
    confidence_threshold: float = Form(default=0.35),
) -> dict[str, Any]:
    """Analyze one live video/dashcam frame in memory without retaining image bytes."""
    segment = store.segments.get(road_segment_id)
    if segment is None:
        raise HTTPException(status_code=422, detail="unknown road segment")
    if frame.content_type and not frame.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="replay frame must be an image")

    conf_clamped = max(0.20, min(0.95, confidence_threshold))
    image_bytes = await frame.read()
    try:
        inference = await asyncio.to_thread(infer_dashcam_frame, image_bytes, conf_clamped, 0.40)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await frame.close()
        image_bytes = b""

    timestamp = _ensure_tz(frame_timestamp)
    lat, lon = segment.definition.polyline[min(1, len(segment.definition.polyline) - 1)]
    published: list[dict[str, Any]] = []
    for candidate in inference["candidates"][:3]:
        if candidate["confidence"] < 0.45:
            continue
        key = (road_segment_id, candidate["label"])
        previous = _replay_last_published.get(key)
        if previous and (timestamp - previous).total_seconds() < REPLAY_EVENT_DEDUP_SECONDS:
            continue
        try:
            result = store.ingest_perception(
                label=candidate["label"],
                confidence=candidate["confidence"],
                bbox_area_ratio=candidate["bbox_area_ratio"],
                model_version=inference["model_version"],
                frame_timestamp=timestamp,
                gnss_samples=[
                    GnssSample(
                        timestamp=timestamp - timedelta(milliseconds=120),
                        location=GeoPoint(lat, lon),
                        accuracy_m=6.0,
                        speed_kph=max(0.0, speed_kph),
                    )
                ],
                attributes={
                    "severity": "high" if candidate["confidence"] >= 0.78 else "medium",
                    "capture_mode": "live_dashcam_feed",
                    "source_label": candidate["source_label"],
                    "plate_mask_applied": True,
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _replay_last_published[key] = timestamp
        published.append(result["event"])

    return {
        "model_version": inference["model_version"],
        "inference_ms": inference["inference_ms"],
        "image_size": inference["image_size"],
        "candidates": inference["candidates"],
        "vehicles": inference["vehicles"],
        "published_events": published,
        "frame_retained": False,
        "dedup_window_seconds": REPLAY_EVENT_DEDUP_SECONDS,
    }


@app.post("/api/events/{event_id}/feedback")
def driver_feedback(event_id: str, body: DriverFeedbackIn) -> dict[str, Any]:
    try:
        return {"event": store.apply_driver_feedback(event_id, body.action)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="event not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/admin/events/{event_id}")
def admin_moderate_event(event_id: str, body: AdminEventModerationIn) -> dict[str, Any]:
    try:
        return {"event": store.moderate_event(event_id, body.workflow_status, body.severity)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="event not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/routes/compare")
def compare_routes(body: RouteCompareIn) -> dict[str, Any]:
    try:
        return store.compare_routes(body.origin, body.destination)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/routes/advisory")
def speed_advisory(body: SpeedAdvisoryIn) -> dict[str, Any]:
    adv = store.compute_advisory(
        body.legal_speed_limit_kph,
        body.hazard,
        body.distance_to_hazard_m,
    )
    return {
        "advisory_speed_kph": adv.advisory_speed_kph,
        "legal_speed_limit_kph": adv.legal_speed_limit_kph,
        "reason": adv.reason,
    }


@app.patch("/api/admin/segments/{segment_id}")
def admin_update_segment(segment_id: str, body: AdminSegmentUpdateIn) -> dict[str, Any]:
    try:
        return store.update_segment(
            segment_id,
            closed=body.closed,
            extra_hazard_penalty=body.extra_hazard_penalty,
            mean_speed_kph=body.mean_speed_kph,
            vehicle_count=body.vehicle_count,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="segment not found") from exc


@app.get("/api/parking")
def list_parking() -> dict[str, Any]:
    items = store.list_parking()
    return {"segments": items, "count": len(items)}


@app.get("/api/admin/fleet")
def admin_fleet() -> dict[str, Any]:
    return store.get_fleet_and_compliance()


@app.get("/api/gis/events.geojson")
def gis_events_geojson() -> JSONResponse:
    return JSONResponse(content=store.events_geojson(), media_type="application/geo+json")


@app.get("/api/gis/segments.geojson")
def gis_segments_geojson() -> JSONResponse:
    return JSONResponse(content=store.segments_geojson(), media_type="application/geo+json")


@app.get("/api/gis/parking.geojson")
def gis_parking_geojson() -> JSONResponse:
    return JSONResponse(content=store.parking_geojson(), media_type="application/geo+json")


@app.get("/api/gis/qgis-project.qgs")
def gis_qgis_project(request: Request) -> Response:
    base_url = str(request.base_url).rstrip("/")
    xml = store.build_qgis_project_xml(base_url)
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="roadsense-bengaluru.qgs"'},
    )


@app.post("/api/admin/simulate-burst")
def admin_simulate_burst() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    seg = store.segments["osm-way-trinity-ejipura"]
    lat, lon = seg.definition.polyline[1]
    return store.ingest_perception(
        label="pothole",
        confidence=0.89,
        bbox_area_ratio=0.055,
        model_version=MODEL_VERSION,
        frame_timestamp=now,
        gnss_samples=[
            GnssSample(
                timestamp=now - timedelta(milliseconds=120),
                location=GeoPoint(lat, lon),
                accuracy_m=4.8,
                speed_kph=28.0,
            )
        ],
        imu_sample=ImuSample(
            timestamp=now - timedelta(milliseconds=80),
            longitudinal_accel_mps2=-3.4,
            vertical_accel_mps2=2.2,
            yaw_rate_dps=1.1,
        ),
        attributes={"severity": "high", "edge_unit": "EDGE-KA01-104", "plate_blur_applied": True},
    )


@app.get("/api/stream")
async def stream_events() -> StreamingResponse:
    queue = store.subscribe()

    async def event_generator():
        try:
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"
            while True:
                try:
                    evt_type, payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {evt_type}\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            store.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
