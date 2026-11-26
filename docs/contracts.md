# Road Event Contract v1

Every module exchanges `RoadEvent` as serialized JSON. Required fields are `event_id`, `category`, `source_type`, `observed_at`, `location`, `confidence`, and `location_accuracy_m`.

```json
{
  "schema_version": "1.0",
  "event_id": "evt_123",
  "category": "pothole",
  "source_type": "camera_observed",
  "observed_at": "2026-11-22T08:30:00+00:00",
  "location": {"latitude": 12.9716, "longitude": 77.5946},
  "location_accuracy_m": 8.5,
  "confidence": 0.88,
  "road_segment_id": "osm-way-42",
  "attributes": {"severity": "medium", "model_version": "perception-0.1"}
}
```

Rules:

- timestamps are timezone-aware ISO-8601 UTC;
- latitude and longitude use WGS-84;
- confidence is `[0, 1]`, combining model and localization confidence where relevant;
- event categories are stable enum values; extend them compatibly;
- `legal_speed_limit_kph` and `advisory_speed_kph` must not be conflated;
- raw imagery, plate text, and direct identifiers are prohibited from `attributes`.
