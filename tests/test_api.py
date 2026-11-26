import io
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from PIL import Image

from backend.main import app
from backend.store import store


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_network_parking_and_fleet(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        network = self.client.get("/api/network")
        self.assertEqual(network.status_code, 200)
        self.assertGreaterEqual(len(network.json()["nodes"]), 10)
        self.assertGreaterEqual(len(network.json()["segments"]), 14)

        parking = self.client.get("/api/parking")
        self.assertEqual(parking.status_code, 200)
        self.assertTrue(all(item["privacy_masked"] for item in parking.json()["segments"]))

        fleet = self.client.get("/api/admin/fleet")
        self.assertEqual(fleet.status_code, 200)
        self.assertEqual(fleet.json()["privacy"]["prohibited_attributes_detected"], 0)

    def test_routes_compare_distinguishes_fastest_from_safest(self):
        res = self.client.post("/api/routes/compare", json={"origin": "cubbon", "destination": "koramangala"})
        self.assertEqual(res.status_code, 200)
        routes = {item["profile"]: item for item in res.json()["routes"]}
        self.assertEqual(set(routes.keys()), {"balanced", "safest", "smoothest", "fastest"})
        self.assertNotEqual(routes["fastest"]["nodes"], routes["safest"]["nodes"])
        self.assertLessEqual(routes["fastest"]["travel_minutes"], routes["safest"]["travel_minutes"])
        self.assertGreater(routes["safest"]["road_quality_score"], routes["fastest"]["road_quality_score"])

    def test_speed_advisory_never_conflates_legal_limit(self):
        near = self.client.post(
            "/api/routes/advisory",
            json={"legal_speed_limit_kph": 50, "hazard": "pothole", "distance_to_hazard_m": 45},
        )
        self.assertEqual(near.status_code, 200)
        payload = near.json()
        self.assertEqual(payload["legal_speed_limit_kph"], 50)
        self.assertEqual(payload["advisory_speed_kph"], 30)
        self.assertIn("pothole", payload["reason"])

        far = self.client.post(
            "/api/routes/advisory",
            json={"legal_speed_limit_kph": 50, "hazard": "pothole", "distance_to_hazard_m": 180},
        )
        self.assertEqual(far.status_code, 200)
        self.assertEqual(far.json()["advisory_speed_kph"], 50)

    def test_perception_ingest_enforces_fusion_confidence_and_privacy(self):
        now = datetime.now(timezone.utc)
        valid = self.client.post(
            "/api/perception/ingest",
            json={
                "label": "pothole",
                "confidence": 0.9,
                "bbox_area_ratio": 0.05,
                "model_version": "yolo11n.pt",
                "frame_timestamp": now.isoformat(),
                "gnss_samples": [
                    {
                        "timestamp": (now - timedelta(milliseconds=120)).isoformat(),
                        "latitude": 12.9756,
                        "longitude": 77.6066,
                        "accuracy_m": 5.0,
                        "speed_kph": 30.0,
                    }
                ],
                "imu_sample": {
                    "timestamp": now.isoformat(),
                    "longitudinal_accel_mps2": -3.5,
                    "vertical_accel_mps2": 1.8,
                    "yaw_rate_dps": 0.5,
                },
                "attributes": {"severity": "high"},
            },
        )
        self.assertEqual(valid.status_code, 200)
        body = valid.json()
        self.assertEqual(body["event"]["source_type"], "camera_observed")
        self.assertTrue(body["fusion"]["harsh_braking_detected"])

        # Stale GNSS (> 750ms) rejected
        stale = self.client.post(
            "/api/perception/ingest",
            json={
                "label": "pothole",
                "confidence": 0.9,
                "bbox_area_ratio": 0.05,
                "model_version": "yolo11n.pt",
                "frame_timestamp": now.isoformat(),
                "gnss_samples": [
                    {
                        "timestamp": (now - timedelta(milliseconds=1400)).isoformat(),
                        "latitude": 12.9756,
                        "longitude": 77.6066,
                        "accuracy_m": 5.0,
                        "speed_kph": 30.0,
                    }
                ],
            },
        )
        self.assertEqual(stale.status_code, 422)
        self.assertIn("stale", stale.json()["detail"].lower())

        # Low confidence (< 0.45) rejected
        low_conf = self.client.post(
            "/api/perception/ingest",
            json={
                "label": "pothole",
                "confidence": 0.30,
                "bbox_area_ratio": 0.05,
                "model_version": "yolo11n.pt",
                "frame_timestamp": now.isoformat(),
                "gnss_samples": [
                    {
                        "timestamp": now.isoformat(),
                        "latitude": 12.9756,
                        "longitude": 77.6066,
                        "accuracy_m": 5.0,
                        "speed_kph": 30.0,
                    }
                ],
            },
        )
        self.assertEqual(low_conf.status_code, 422)

        # Prohibited PII attributes rejected
        pii_attempt = self.client.post(
            "/api/perception/ingest",
            json={
                "label": "pothole",
                "confidence": 0.9,
                "bbox_area_ratio": 0.05,
                "model_version": "yolo11n.pt",
                "frame_timestamp": now.isoformat(),
                "gnss_samples": [
                    {
                        "timestamp": now.isoformat(),
                        "latitude": 12.9756,
                        "longitude": 77.6066,
                        "accuracy_m": 5.0,
                        "speed_kph": 30.0,
                    }
                ],
                "attributes": {"plate_text": "KA01AB1234", "raw_image": "base64"},
            },
        )
        self.assertEqual(pii_attempt.status_code, 422)
        self.assertIn("privacy", pii_attempt.json()["detail"].lower())

    def test_admin_road_closure_reroutes_and_moderation_updates_event(self):
        # Close a segment on the fastest corridor, confirm fastest avoids it, then reopen
        close_res = self.client.patch("/api/admin/segments/osm-way-richmond-shanthi", json={"closed": True})
        self.assertEqual(close_res.status_code, 200)
        routes_res = self.client.post("/api/routes/compare", json={"origin": "cubbon", "destination": "koramangala"})
        fastest = next(r for r in routes_res.json()["routes"] if r["profile"] == "fastest")
        self.assertNotIn("osm-way-richmond-shanthi", fastest["segment_ids"])

        # Reopen cleanly
        reopen_res = self.client.patch("/api/admin/segments/osm-way-richmond-shanthi", json={"closed": False})
        self.assertEqual(reopen_res.status_code, 200)

        # Moderate event and send feedback
        mod = self.client.patch(
            "/api/admin/events/evt_bng_pothole_11",
            json={"workflow_status": "verified", "severity": "high"},
        )
        self.assertEqual(mod.status_code, 200)
        self.assertEqual(mod.json()["event"]["workflow_status"], "verified")
        self.assertEqual(mod.json()["event"]["attributes"]["severity"], "high")

        fb = self.client.post("/api/events/evt_bng_pothole_11/feedback", json={"action": "confirm"})
        self.assertEqual(fb.status_code, 200)
        self.assertEqual(fb.json()["event"]["confirmations"], 1)

        # Restore original status
        store.moderate_event("evt_bng_pothole_11", "active", "low")

    def test_gis_geojson_and_qgis_project_endpoints(self):
        events_geo = self.client.get("/api/gis/events.geojson")
        self.assertEqual(events_geo.status_code, 200)
        ev_fc = events_geo.json()
        self.assertEqual(ev_fc["type"], "FeatureCollection")
        self.assertGreater(len(ev_fc["features"]), 0)
        pt = ev_fc["features"][0]["geometry"]["coordinates"]
        # GeoJSON order strictly [lon, lat] -> Bengaluru ~[77.x, 12.x]
        self.assertGreater(pt[0], 70.0)
        self.assertLess(pt[1], 20.0)

        segs_geo = self.client.get("/api/gis/segments.geojson")
        self.assertEqual(segs_geo.status_code, 200)
        self.assertEqual(segs_geo.json()["type"], "FeatureCollection")
        line = segs_geo.json()["features"][0]["geometry"]["coordinates"]
        self.assertGreater(line[0][0], 70.0)
        self.assertLess(line[0][1], 20.0)

        park_geo = self.client.get("/api/gis/parking.geojson")
        self.assertEqual(park_geo.status_code, 200)
        self.assertEqual(park_geo.json()["type"], "FeatureCollection")
        self.assertTrue(all(f["properties"]["privacy_masked"] for f in park_geo.json()["features"]))

        qgs = self.client.get("/api/gis/qgis-project.qgs")
        self.assertEqual(qgs.status_code, 200)
        self.assertIn("<qgis", qgs.text)
        self.assertIn("/api/gis/events.geojson", qgs.text)

    def test_dashcam_feeds_ssrf_guard_and_replay_frame_inference(self):
        feeds = self.client.get("/api/dashcam/feeds")
        self.assertEqual(feeds.status_code, 200)
        self.assertGreaterEqual(len(feeds.json()["feeds"]), 2)

        # SSRF guard blocks loopback / private stream URLs
        blocked = self.client.get("/api/dashcam/stream", params={"url": "http://127.0.0.1:8000/secret.mp4"})
        self.assertEqual(blocked.status_code, 422)

        # In-memory YOLO frame inference test without retaining frame bytes
        buf = io.BytesIO()
        Image.new("RGB", (320, 240), color=(40, 45, 50)).save(buf, format="JPEG")
        buf.seek(0)
        resp = self.client.post(
            "/api/perception/replay-frame",
            data={
                "road_segment_id": "osm-way-richmond-shanthi",
                "frame_timestamp": datetime.now(timezone.utc).isoformat(),
                "speed_kph": "30",
                "confidence_threshold": "0.35",
            },
            files={"frame": ("frame.jpg", buf, "image/jpeg")},
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertFalse(payload["frame_retained"])
        self.assertIsInstance(payload["candidates"], list)
        self.assertIsInstance(payload["vehicles"], list)
        self.assertGreaterEqual(payload["inference_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()

