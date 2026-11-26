"""
Locust load test for the Road Intelligence Platform.

Simulates realistic mixed traffic against the API with weighted task distribution:
  - Health checks         (weight 1) — lightweight liveness polling
  - Nearby event queries  (weight 5) — dominant read workload
  - Telemetry ingestion   (weight 3) — write workload
  - Parking availability  (weight 2) — secondary read workload

Target profile:
    locust -f tests/performance/locustfile.py \
           --host http://localhost:8000 \
           --users 200 \
           --spawn-rate 10 \
           --run-time 5m \
           --headless

Or launch the web UI (default port 8089):
    locust -f tests/performance/locustfile.py --host http://localhost:8000
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone

from locust import HttpUser, between, task
from locust.exception import RescheduleTask


# ── Geographic bounds — National Capital Territory, Delhi ───────────────────

LAT_MIN = 28.40
LAT_MAX = 28.88
LON_MIN = 76.84
LON_MAX = 77.35

# Fixed hotspot for read queries (Connaught Place)
HOTSPOT_LAT = 28.6315
HOTSPOT_LON = 77.2167

# Event types and severities to randomise payload content
EVENT_TYPES = ["pothole", "road_crack", "waterlogging", "debris", "road_damage", "speed_bump"]
SEVERITIES = ["low", "medium", "high", "critical"]
SOURCES = ["mobile_crowdsource", "iot_sensor", "satellite_scan", "field_survey"]


def _random_coords() -> tuple[float, float]:
    """Return a random lat/lon pair within the NCT Delhi bounding box."""
    lat = round(random.uniform(LAT_MIN, LAT_MAX), 6)
    lon = round(random.uniform(LON_MIN, LON_MAX), 6)
    return lat, lon


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── User Behaviour Class ─────────────────────────────────────────────────────

class RoadIntelligenceUser(HttpUser):
    """
    Simulates a mixed client workload against the Road Intelligence API.

    wait_time: 0.5–2 s between tasks — approximates realistic user/sensor cadence.
    """

    wait_time = between(0.5, 2.0)

    # ── Health Check ─────────────────────────────────────────────────────────

    @task(1)
    def health_check(self) -> None:
        """GET /health — lightweight availability probe."""
        with self.client.get(
            "/health",
            name="/health",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                if body.get("status") != "healthy":
                    response.failure(
                        f"Health check returned unhealthy body: {body}"
                    )
                else:
                    response.success()
            else:
                response.failure(
                    f"Health check returned HTTP {response.status_code}"
                )

    # ── Nearby Events Query ──────────────────────────────────────────────────

    @task(5)
    def get_nearby_events(self) -> None:
        """
        GET /events/nearby — most common read operation.
        Queries from the central hotspot with a 1 km radius.
        """
        params = {
            "lat": HOTSPOT_LAT,
            "lon": HOTSPOT_LON,
            "radius": 1000,
        }
        with self.client.get(
            "/events/nearby",
            params=params,
            name="/events/nearby",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if not isinstance(data, list):
                    response.failure(f"Expected list, got {type(data).__name__}")
                else:
                    response.success()
            elif response.status_code == 404:
                # No events near location is a valid business state
                response.success()
            else:
                response.failure(
                    f"GET /events/nearby returned HTTP {response.status_code}"
                )

    # ── Telemetry Ingestion ──────────────────────────────────────────────────

    @task(3)
    def ingest_telemetry(self) -> None:
        """
        POST /ingest/telemetry — simulates IoT sensor or mobile app reporting
        a road defect event from a random location in Delhi.
        """
        lat, lon = _random_coords()
        payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": random.choice(EVENT_TYPES),
            "severity": random.choice(SEVERITIES),
            "latitude": lat,
            "longitude": lon,
            "reported_at": _iso_now(),
            "source": random.choice(SOURCES),
            "metadata": {
                "confidence": round(random.uniform(0.6, 0.99), 2),
                "speed_kmh": random.randint(0, 80),
                "device_id": f"device-{random.randint(1000, 9999)}",
            },
        }

        with self.client.post(
            "/ingest/telemetry",
            json=payload,
            name="/ingest/telemetry",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201):
                response.success()
            elif response.status_code == 422:
                # Validation error — log as failure with detail
                response.failure(
                    f"Validation error on ingest: {response.text[:200]}"
                )
            elif response.status_code == 429:
                # Rate limited — reschedule task instead of recording failure
                raise RescheduleTask()
            else:
                response.failure(
                    f"POST /ingest/telemetry returned HTTP {response.status_code}"
                )

    # ── Parking Availability Query ───────────────────────────────────────────

    @task(2)
    def get_parking_availability(self) -> None:
        """
        GET /parking/availability — queries parking occupancy near the hotspot.
        Mixes exact hotspot and slightly varied coordinates to avoid caching artefacts.
        """
        # 70% of the time use exact hotspot, 30% use slight random offset
        if random.random() < 0.70:
            lat, lon = HOTSPOT_LAT, HOTSPOT_LON
        else:
            lat = round(HOTSPOT_LAT + random.uniform(-0.01, 0.01), 6)
            lon = round(HOTSPOT_LON + random.uniform(-0.01, 0.01), 6)

        params = {
            "lat": lat,
            "lon": lon,
            "radius": 500,
        }
        with self.client.get(
            "/parking/availability",
            params=params,
            name="/parking/availability",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if not isinstance(data, list):
                    response.failure(
                        f"Expected list from parking availability, got {type(data).__name__}"
                    )
                else:
                    response.success()
            elif response.status_code == 404:
                response.success()
            else:
                response.failure(
                    f"GET /parking/availability returned HTTP {response.status_code}"
                )

    # ── BBox Road Events Query ───────────────────────────────────────────────

    @task(1)
    def get_events_by_bbox(self) -> None:
        """
        GET /events?bbox=... — bounding-box query simulating a map viewport request.
        Generates a random small viewport (~2 km × 2 km) within Delhi.
        """
        lat, lon = _random_coords()
        delta = 0.009  # ~1 km in degrees at this latitude

        bbox = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"
        with self.client.get(
            "/events",
            params={"bbox": bbox},
            name="/events?bbox",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                response.success()
            else:
                response.failure(
                    f"GET /events?bbox returned HTTP {response.status_code}"
                )

    # ── Road Segment Score Read ──────────────────────────────────────────────

    @task(1)
    def get_road_segment_list(self) -> None:
        """
        GET /segments/ — paginated list of road segments.
        Simulates a dashboard widget fetching segment data.
        """
        params = {
            "lat": HOTSPOT_LAT,
            "lon": HOTSPOT_LON,
            "radius": 2000,
            "limit": 20,
            "offset": random.randint(0, 5) * 20,
        }
        with self.client.get(
            "/segments/",
            params=params,
            name="/segments/",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 404):
                response.success()
            else:
                response.failure(
                    f"GET /segments/ returned HTTP {response.status_code}"
                )


# ── Load Shape ───────────────────────────────────────────────────────────────
# Uncomment to use a stepped load profile instead of the CLI --users flag.
#
# from locust import LoadTestShape
#
# class SteppedLoadShape(LoadTestShape):
#     """Ramp up in steps: 50 → 100 → 200 users, hold 5 min each, then ramp down."""
#
#     stages = [
#         {"duration": 60,  "users": 50,  "spawn_rate": 10},
#         {"duration": 180, "users": 100, "spawn_rate": 10},
#         {"duration": 300, "users": 200, "spawn_rate": 10},
#         {"duration": 420, "users": 100, "spawn_rate": 20},
#         {"duration": 480, "users": 50,  "spawn_rate": 20},
#         {"duration": 540, "users": 0,   "spawn_rate": 50},
#     ]
#
#     def tick(self):
#         run_time = self.get_run_time()
#         for stage in self.stages:
#             if run_time < stage["duration"]:
#                 return stage["users"], stage["spawn_rate"]
#         return None
