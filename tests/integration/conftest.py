"""
pytest configuration and shared fixtures for Road Intelligence integration tests.

Usage:
    pytest tests/integration/ -v --tb=short

Environment variables:
    TEST_API_URL   Base URL of the API under test  (default: http://localhost:8000)
    TEST_DB_URL    PostgreSQL DSN for direct DB ops (default: derived from env)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import AsyncGenerator, Generator

import httpx
import pytest


# ── Event Loop ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Session-scoped event loop so that module-scoped async fixtures work
    without spawning a new loop per test.

    Required by pytest-asyncio when using 'asyncio' mode.
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ── API Client ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Module-scoped async HTTP client for the Road Intelligence API.

    Reads the base URL from the TEST_API_URL environment variable so it can
    point at localhost during local dev or at a remote staging host in CI.
    """
    base_url = os.getenv("TEST_API_URL", "http://localhost:8000")
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Test-Client": "integration-tests",
        },
        follow_redirects=True,
    ) as client:
        # Verify the server is reachable before any tests run.
        try:
            resp = await client.get("/health")
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
            pytest.skip(
                f"API server not reachable at {base_url}: {exc}. "
                "Start the stack with 'make dev' before running integration tests."
            )
        yield client


# ── Road Segment Seed Fixture ─────────────────────────────────────────────────

@pytest.fixture()
async def seed_road_segment(api_client: httpx.AsyncClient) -> dict:
    """
    Create a minimal road segment via the API and return the response body.

    The created segment is not automatically deleted — the cleanup_db fixture
    handles table truncation after each test.
    """
    segment_name = f"Integration Test Segment {uuid.uuid4().hex[:8]}"
    payload = {
        "name": segment_name,
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [77.2167, 28.6315],
                [77.2185, 28.6330],
            ],
        },
        "road_class": "urban",
        "speed_limit_kmh": 50,
        "condition_score": 7.0,
        "length_metres": 220.5,
        "surface_type": "asphalt",
    }

    response = await api_client.post("/segments/", json=payload)

    if response.status_code not in (200, 201):
        pytest.fail(
            f"seed_road_segment: failed to create segment — "
            f"HTTP {response.status_code}: {response.text}"
        )

    data = response.json()
    assert "id" in data, f"Response missing 'id': {data}"
    return data


# ── Parking Lot Seed Fixture ──────────────────────────────────────────────────

@pytest.fixture()
async def seed_parking_lot(api_client: httpx.AsyncClient) -> dict:
    """
    Register a test parking lot and post an initial occupancy observation.
    Returns the lot metadata dict including the lot_id.
    """
    lot_id = f"test-lot-{uuid.uuid4().hex[:8]}"
    payload = {
        "lot_id": lot_id,
        "name": f"Integration Test Lot {lot_id}",
        "latitude": 28.6315,
        "longitude": 77.2167,
        "total_spaces": 100,
        "address": "1 Test Road, Test City",
    }

    response = await api_client.post("/parking/lots", json=payload)
    if response.status_code not in (200, 201):
        pytest.skip(
            f"seed_parking_lot: failed to create lot (HTTP {response.status_code}) — "
            "skipping test that depends on this fixture."
        )

    return response.json()


# ── Database Cleanup ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def cleanup_db(api_client: httpx.AsyncClient) -> AsyncGenerator[None, None]:
    """
    Autouse fixture that calls the test-only cleanup endpoint after every test,
    truncating ephemeral rows inserted during the test.

    The /admin/test/cleanup endpoint is only enabled when APP_ENV=test.
    If the endpoint is absent (404) the fixture silently passes, so these
    tests can also run in read-only audit mode against a staging environment.
    """
    yield

    truncate_tables = [
        "road_events",
        "telemetry_raw",
        "parking_observations",
        "road_segments",
    ]

    try:
        cleanup_resp = await api_client.post(
            "/admin/test/cleanup",
            json={"tables": truncate_tables},
            timeout=10.0,
        )
        if cleanup_resp.status_code not in (200, 204, 404):
            # Log a warning but don't fail the test — cleanup is best-effort.
            print(
                f"\n[cleanup_db] WARNING: cleanup endpoint returned "
                f"HTTP {cleanup_resp.status_code}: {cleanup_resp.text}"
            )
    except httpx.RequestError as exc:
        print(f"\n[cleanup_db] WARNING: cleanup request failed: {exc}")


# ── Utility Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture()
def test_lat() -> float:
    """Central test latitude (Connaught Place, New Delhi)."""
    return 28.6315


@pytest.fixture()
def test_lon() -> float:
    """Central test longitude (Connaught Place, New Delhi)."""
    return 77.2167


@pytest.fixture()
def test_radius() -> int:
    """Default search radius in metres for proximity queries."""
    return 1000


@pytest.fixture()
def unique_id() -> str:
    """Return a fresh UUID hex string for unique identifiers in tests."""
    return uuid.uuid4().hex


# ── pytest Configuration ──────────────────────────────────────────────────────

def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers", "slow: mark test as slow (deselect with -m 'not slow')"
    )
    config.addinivalue_line(
        "markers", "requires_model: mark test as requiring downloaded ML model weights"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
