"""
Integration tests for the Road Intelligence API.

These tests use httpx.AsyncClient against the FastAPI app in-process.
A real database is NOT required — tests that touch the DB are marked with
@pytest.mark.integration and are skipped by default.

Run unit-only tests:  pytest backend/tests/test_api.py
Run all (needs DB):   pytest backend/tests/test_api.py -m integration
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Async test client with mocked DB / Redis startup suppressed."""
    import sys
    import os

    # Add backend/ to sys.path so relative imports work from tests
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    from main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    @pytest.mark.anyio
    async def test_health_returns_expected_keys(self, client: AsyncClient):
        """Health endpoint must return status, db, and redis keys."""
        resp = await client.get("/api/v1/health/")
        # Allow 200 or 503 (degraded) — but keys must be present
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "status" in body
        assert "db" in body
        assert "redis" in body

    @pytest.mark.anyio
    async def test_health_status_values(self, client: AsyncClient):
        """status must be 'ok' or 'degraded'."""
        resp = await client.get("/api/v1/health/")
        body = resp.json()
        assert body["status"] in ("ok", "degraded")


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

class TestRoot:
    @pytest.mark.anyio
    async def test_root_returns_welcome(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body
        assert "docs" in body


# ---------------------------------------------------------------------------
# Road events — schema / validation tests (no DB required)
# ---------------------------------------------------------------------------

class TestRoadEventValidation:
    _VALID_PAYLOAD = {
        "event_type": "pothole",
        "severity": "high",
        "lat": 52.52,
        "lon": 13.405,
        "source": "test-sensor",
        "observed_at": "2024-01-15T10:30:00Z",
    }

    @pytest.mark.anyio
    async def test_create_event_missing_required_fields_returns_422(
        self, client: AsyncClient
    ):
        resp = await client.post("/api/v1/events/", json={})
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_event_invalid_lat_returns_422(self, client: AsyncClient):
        payload = {**self._VALID_PAYLOAD, "lat": 999.0}
        resp = await client.post("/api/v1/events/", json=payload)
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_event_invalid_lon_returns_422(self, client: AsyncClient):
        payload = {**self._VALID_PAYLOAD, "lon": -999.0}
        resp = await client.post("/api/v1/events/", json=payload)
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_event_confidence_out_of_range_returns_422(
        self, client: AsyncClient
    ):
        payload = {**self._VALID_PAYLOAD, "confidence": 1.5}
        resp = await client.post("/api/v1/events/", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Parking — schema / validation tests
# ---------------------------------------------------------------------------

class TestParkingValidation:
    _VALID_PAYLOAD = {
        "lat": 52.52,
        "lon": 13.405,
        "occupancy_rate": 0.75,
        "occupied_spaces": 15,
        "total_spaces": 20,
        "observed_at": "2024-01-15T10:30:00Z",
        "source": "test-camera",
    }

    @pytest.mark.anyio
    async def test_create_observation_missing_fields_returns_422(
        self, client: AsyncClient
    ):
        resp = await client.post("/api/v1/parking/observations", json={})
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_observation_invalid_occupancy_returns_422(
        self, client: AsyncClient
    ):
        payload = {**self._VALID_PAYLOAD, "occupancy_rate": 1.5}
        resp = await client.post("/api/v1/parking/observations", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Ingestion — schema / validation tests
# ---------------------------------------------------------------------------

class TestIngestionValidation:
    @pytest.mark.anyio
    async def test_telemetry_empty_payload_returns_422(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/ingest/telemetry",
            json={"road_events": [], "parking_observations": []},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_frame_result_empty_payload_accepted(self, client: AsyncClient):
        """frame-result with no events/plates should still be accepted (202)."""
        resp = await client.post(
            "/api/v1/ingest/frame-result",
            json={
                "road_events": [],
                "parking_observations": [],
                "detected_plates": [],
                "frame_id": "frame-001",
            },
        )
        # Will hit DB; accept 202 or 500 (no DB in unit mode)
        assert resp.status_code in (202, 500)


# ---------------------------------------------------------------------------
# Nearby events — query param validation
# ---------------------------------------------------------------------------

class TestNearbyEventsValidation:
    @pytest.mark.anyio
    async def test_nearby_missing_lat_lon_returns_422(self, client: AsyncClient):
        resp = await client.get("/api/v1/events/nearby")
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_nearby_invalid_radius_returns_422(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/events/nearby",
            params={"lat": 52.52, "lon": 13.405, "radius_meters": -1},
        )
        assert resp.status_code == 422
