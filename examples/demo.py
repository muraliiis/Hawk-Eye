from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

from road_intelligence.contracts import GeoPoint
from road_intelligence.perception import Detection, PerceptionNormalizer
from road_intelligence.routing import RoadEdge, Router
from road_intelligence.sensor_fusion import GnssSample, SensorFusion

now = datetime.now(timezone.utc)
fusion = SensorFusion([GnssSample(now, GeoPoint(12.9716, 77.5946), 6, 32)])
estimate = fusion.locate(now)
event = PerceptionNormalizer().normalize(Detection("pothole", 0.91, now, 0.06, "yolo-road-v1"), estimate.location, estimate.accuracy_m)
print(event.to_dict())

router = Router([RoadEdge("A", "B", 2.2, 5, hazard_penalty=3), RoadEdge("A", "C", 2.7, 6), RoadEdge("C", "B", 1.1, 2)])
print(router.route("A", "B", "safest"))
print(router.speed_advisory(50, "pothole", 45))
