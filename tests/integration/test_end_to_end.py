"""
End-to-end integration tests for the Road Intelligence Platform.

These tests assume a running API server. Configure the base URL via the
TEST_API_URL environment variable (default: http://localhost:8000).

Run with:
    pytest tests/integration/test_end_to_end.py -v --tb=short
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import pytest
import httpx

# Base URL is configured via environment variable for flexibility across
# local dev, CI, and staging environments.
BASE_URL = os.getenv("TEST_API_URL", "http://localhost:8000")

# Coordinates for testing — central Delhi (Connaught Place area)
TEST_LAT = 28.6315
TEST_LON = 77.2167
TEST_RADIUS = 1000  # metres


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
async def api_client() -> httpx.AsyncClient:
    """Module-scoped async HTTP client pointing at the test API."""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx.Timeout(30.0),
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.fixture()
async def seed_road_segment(api_client: httpx.AsyncClient) -> dict[str, Any]:
    """Create a test road segment and return the response body."""
    payload = {
        "name": f"Test Segment {uuid.uuid4().hex[:8]}",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [TEST_LON, TEST_LAT],
                [TEST_LON + 0.001, TEST_LAT + 0.001],
            ],
        },
        "road_class": "urban",
        "speed_limit_kmh": 50,
        "condition_score": 7.5,
    }
    response = await api_client.post("/segments/", json=payload)
    assert response.status_code in (200, 201), (
        f"Failed to create seed road segment: {response.status_code} {response.text}"
    )
    return response.json()


@pytest.fixture(autouse=True)
async def cleanup_db(api_client: httpx.AsyncClient):
    """Truncate test data after each test to maintain isolation."""
    yield
    # Request the test-only cleanup endpoint which truncates ephemeral test rows.
    # In production, this endpoint is disabled; it is enabled when APP_ENV=test.
    cleanup_response = await api_client.post(
        "/admin/test/cleanup",
        json={"tables": ["road_events", "parking_observations", "telemetry_raw"]},
    )
    # Tolerate 404 when running against a production build that omits the endpoint.
    if cleanup_response.status_code not in (200, 204, 404):
        pytest.fail(
            f"Cleanup endpoint returned unexpected status: "
            f"{cleanup_response.status_code} {cleanup_response.text}"
        )


# ── Test Cases ───────────────────────────────────────────────────────────────

class TestHealthCheck:
    """Service liveness and dependency health."""

    @pytest.mark.anyio
    async def test_health_check(self, api_client: httpx.AsyncClient) -> None:
        """GET /health should return 200 with db and redis connected."""
        response = await api_client.get("/health")

        assert response.status_code == 200, (
            f"Health check failed with status {response.status_code}: {response.text}"
        )

        body = response.json()
        assert body.get("status") == "healthy", f"Unexpected status: {body}"
        assert body.get("database") == "connected", f"Database not connected: {body}"
        assert body.get("redis") == "connected", f"Redis not connected: {body}"

    @pytest.mark.anyio
    async def test_health_check_includes_version(
        self, api_client: httpx.AsyncClient
    ) -> None:
        """Health endpoint should expose a version field."""
        response = await api_client.get("/health")
        body = response.json()
        assert "version" in body, f"Missing 'version' in health response: {body}"


class TestRoadEventIngestion:
    """Telemetry ingestion and nearby event retrieval."""

    @pytest.mark.anyio
    async def test_ingest_road_event_and_retrieve(
        self, api_client: httpx.AsyncClient
    ) -> None:
        """
        POST /ingest/telemetry with a pothole event at a known location,
        then GET /events/nearby confirms the event is returned.
        """
        event_id = str(uuid.uuid4())
        ingest_payload = {
            "event_id": event_id,
            "event_type": "pothole",
            "severity": "high",
            "latitude": TEST_LAT,
            "longitude": TEST_LON,
            "reported_at": "2024-06-01T10:00:00Z",
            "source": "mobile_crowdsource",
            "metadata": {"depth_cm": 8, "confidence": 0.91},
        }

        ingest_resp = await api_client.post("/ingest/telemetry", json=ingest_payload)
        assert ingest_resp.status_code in (200, 201), (
            f"Ingest failed: {ingest_resp.status_code} {ingest_resp.text}"
        )

        # Allow a brief moment for async processing if needed
        await _async_sleep(0.2)

        nearby_resp = await api_client.get(
            "/events/nearby",
            params={"lat": TEST_LAT, "lon": TEST_LON, "radius": TEST_RADIUS},
        )
        assert nearby_resp.status_code == 200, (
            f"Nearby query failed: {nearby_resp.status_code} {nearby_resp.text}"
        )

        events = nearby_resp.json()
        assert isinstance(events, list), f"Expected list, got: {type(events)}"
        assert len(events) >= 1, "No events returned near the ingested location"

        # Confirm our specific event is in the response
        returned_ids = [e.get("event_id") for e in events]
        assert event_id in returned_ids, (
            f"Ingested event {event_id} not found in nearby results: {returned_ids}"
        )

    @pytest.mark.anyio
    async def test_ingest_validates_severity(
        self, api_client: httpx.AsyncClient
    ) -> None:
        """POST /ingest/telemetry with invalid severity should return 422."""
        payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "pothole",
            "severity": "INVALID_SEVERITY",
            "latitude": TEST_LAT,
            "longitude": TEST_LON,
            "reported_at": "2024-06-01T10:00:00Z",
            "source": "test",
        }
        response = await api_client.post("/ingest/telemetry", json=payload)
        assert response.status_code == 422, (
            f"Expected 422 for invalid severity, got {response.status_code}"
        )

    @pytest.mark.anyio
    async def test_bbox_query_road_events(
        self, api_client: httpx.AsyncClient
    ) -> None:
        """
        Ingest events at known coordinates, then GET /events?bbox=... returns them.
        """
        # Ingest three events inside the bounding box
        events_inside: list[str] = []
        for i in range(3):
            eid = str(uuid.uuid4())
            payload = {
                "event_id": eid,
                "event_type": "road_crack",
                "severity": "medium",
                "latitude": TEST_LAT + i * 0.0005,
                "longitude": TEST_LON + i * 0.0005,
                "reported_at": "2024-06-01T11:00:00Z",
                "source": "test_bbox",
            }
            resp = await api_client.post("/ingest/telemetry", json=payload)
            assert resp.status_code in (200, 201)
            events_inside.append(eid)

        # Ingest one event clearly outside the bbox
        outside_eid = str(uuid.uuid4())
        outside_payload = {
            "event_id": outside_eid,
            "event_type": "pothole",
            "severity": "low",
            "latitude": TEST_LAT + 5.0,
            "longitude": TEST_LON + 5.0,
            "reported_at": "2024-06-01T11:00:00Z",
            "source": "test_bbox_outside",
        }
        await api_client.post("/ingest/telemetry", json=outside_payload)

        # Query with a tight bbox around the inside events
        bbox_resp = await api_client.get(
            "/events",
            params={
                "bbox": f"{TEST_LON - 0.01},{TEST_LAT - 0.01},{TEST_LON + 0.01},{TEST_LAT + 0.01}",
            },
        )
        assert bbox_resp.status_code == 200, (
            f"BBox query failed: {bbox_resp.status_code} {bbox_resp.text}"
        )

        result_ids = {e.get("event_id") for e in bbox_resp.json()}
        for eid in events_inside:
            assert eid in result_ids, f"Event {eid} should be inside bbox but was not returned"
        assert outside_eid not in result_ids, "Outside event should not appear in bbox results"


class TestParkingFlow:
    """Parking observation ingestion and availability queries."""

    @pytest.mark.anyio
    async def test_parking_observation_flow(
        self, api_client: httpx.AsyncClient
    ) -> None:
        """
        POST /parking/observations adds a parking event,
        GET /parking/availability returns the updated state.
        """
        lot_id = f"test-lot-{uuid.uuid4().hex[:6]}"
        obs_payload = {
            "lot_id": lot_id,
            "timestamp": "2024-06-01T12:00:00Z",
            "total_spaces": 100,
            "occupied_spaces": 45,
            "latitude": TEST_LAT,
            "longitude": TEST_LON,
            "source": "anpr_camera",
            "confidence": 0.97,
        }

        obs_resp = await api_client.post("/parking/observations", json=obs_payload)
        assert obs_resp.status_code in (200, 201), (
            f"Observation POST failed: {obs_resp.status_code} {obs_resp.text}"
        )

        avail_resp = await api_client.get(
            "/parking/availability",
            params={"lat": TEST_LAT, "lon": TEST_LON, "radius": 500},
        )
        assert avail_resp.status_code == 200, (
            f"Availability GET failed: {avail_resp.status_code} {avail_resp.text}"
        )

        lots = avail_resp.json()
        assert isinstance(lots, list), f"Expected list, got {type(lots)}"

        matched = [lot for lot in lots if lot.get("lot_id") == lot_id]
        assert len(matched) == 1, (
            f"Expected to find lot {lot_id} in availability results. Got: {lots}"
        )

        lot = matched[0]
        assert lot.get("total_spaces") == 100
        assert lot.get("occupied_spaces") == 45
        assert lot.get("available_spaces") == 55

    @pytest.mark.anyio
    async def test_parking_observation_requires_lot_id(
        self, api_client: httpx.AsyncClient
    ) -> None:
        """Missing lot_id should trigger a 422 validation error."""
        response = await api_client.post(
            "/parking/observations",
            json={"occupied_spaces": 10, "total_spaces": 50},
        )
        assert response.status_code == 422


class TestRoadSegmentScoring:
    """Road segment CRUD and score update operations."""

    @pytest.mark.anyio
    async def test_road_segment_score_update(
        self,
        api_client: httpx.AsyncClient,
        seed_road_segment: dict[str, Any],
    ) -> None:
        """
        PUT /segments/{id}/score updates the score;
        GET /segments/{id} reflects the new value.
        """
        segment_id = seed_road_segment["id"]
        new_score = 3.2

        update_resp = await api_client.put(
            f"/segments/{segment_id}/score",
            json={"condition_score": new_score, "reason": "post-rain inspection"},
        )
        assert update_resp.status_code in (200, 204), (
            f"Score update failed: {update_resp.status_code} {update_resp.text}"
        )

        get_resp = await api_client.get(f"/segments/{segment_id}")
        assert get_resp.status_code == 200, (
            f"Segment GET failed: {get_resp.status_code} {get_resp.text}"
        )

        segment = get_resp.json()
        assert segment.get("condition_score") == pytest.approx(new_score, abs=0.01), (
            f"Score not updated — expected {new_score}, got {segment.get('condition_score')}"
        )

    @pytest.mark.anyio
    async def test_segment_score_out_of_range(
        self,
        api_client: httpx.AsyncClient,
        seed_road_segment: dict[str, Any],
    ) -> None:
        """Score values outside [0, 10] should return 422."""
        segment_id = seed_road_segment["id"]
        response = await api_client.put(
            f"/segments/{segment_id}/score",
            json={"condition_score": 15.0},
        )
        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_get_nonexistent_segment(
        self, api_client: httpx.AsyncClient
    ) -> None:
        """GET /segments/{id} with unknown UUID should return 404."""
        fake_id = str(uuid.uuid4())
        response = await api_client.get(f"/segments/{fake_id}")
        assert response.status_code == 404


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _async_sleep(seconds: float) -> None:
    """Non-blocking sleep for use inside async tests."""
    import asyncio
    await asyncio.sleep(seconds)
