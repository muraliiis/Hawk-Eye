import unittest
from datetime import datetime, timedelta, timezone

from road_intelligence.contracts import GeoPoint, VehicleObservation
from road_intelligence.perception import Detection, PerceptionNormalizer
from road_intelligence.routing import RoadEdge, Router
from road_intelligence.sensor_fusion import GnssSample, SensorFusion
from road_intelligence.traffic import TrafficIntelligence


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.point = GeoPoint(12.9716, 77.5946)

    def test_perception_filters_low_confidence_and_normalizes(self):
        normalizer = PerceptionNormalizer()
        self.assertIsNone(normalizer.normalize(Detection("pothole", .2, self.now), self.point, 5))
        event = normalizer.normalize(Detection("pothole", .9, self.now, .03, "v1"), self.point, 5, "s1")
        self.assertEqual(event.category, "pothole")
        self.assertEqual(event.road_segment_id, "s1")
        self.assertLess(event.confidence, .9)

    def test_fusion_rejects_stale_and_map_matches(self):
        fusion = SensorFusion([GnssSample(self.now, self.point, 5, 25)])
        result = fusion.locate(self.now + timedelta(milliseconds=400), {"s1": self.point})
        self.assertEqual(result.road_segment_id, "s1")
        with self.assertRaises(ValueError):
            fusion.locate(self.now + timedelta(seconds=2))

    def test_traffic_infers_congestion(self):
        traffic = TrafficIntelligence()
        state = traffic.summarize([VehicleObservation("s1", self.now, 10), VehicleObservation("s1", self.now, 20)], 50)
        self.assertTrue(state.is_congested)
        self.assertIsNotNone(traffic.congestion_event(state, self.point, self.now))

    def test_routing_profiles_and_advisory(self):
        router = Router([RoadEdge("A", "B", 1, 5, hazard_penalty=10), RoadEdge("A", "C", 2, 6), RoadEdge("C", "B", 1, 2)])
        self.assertEqual(router.route("A", "B", "safest").nodes, ("A", "C", "B"))
        advice = router.speed_advisory(50, "pothole", 60)
        self.assertEqual((advice.advisory_speed_kph, advice.legal_speed_limit_kph), (30, 50))


if __name__ == "__main__":
    unittest.main()
