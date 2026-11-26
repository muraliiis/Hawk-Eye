# Architecture and integration plan

## Data flow

```text
Dashcam frames ─> Perception adapter ─┐
GNSS + IMU ────> Sensor fusion ───────┼─> RoadEvent stream -> geospatial/event store
Partner traffic + telemetry ─> Traffic ┘                            │
                                                              Routing engine
                                                                   │
                                              navigation UI / backend API / alerts
```

All events retain `source_type`, `observed_at`, `confidence`, and a location uncertainty radius. `source_type` distinguishes a camera observation from an inferred aggregate or external provider result, so downstream applications never present inference as a direct observation.

## Ownership and hand-off contracts

1. Perception receives frame-local model output only; it does not assign a final geographic position. It creates a provisional event with the camera-frame timestamp.
2. Sensor Fusion chooses/interpolates the closest GNSS state, assigns `location`, `location_accuracy_m`, optional `road_segment_id`, and rejects stale matches.
3. Traffic consumes anonymous segment observations. It emits a `TRAFFIC_CONGESTION` or `INCIDENT` event only with a clearly marked inferred/external source.
4. Routing consumes published segment conditions and returns alternatives. Legal speed limits remain a separate field; an advisory is never represented as a legal limit.

## Production boundaries

- Edge: hardware timestamping, model inference, buffering for offline uploads, anonymization before upload.
- Cloud: authenticated ingestion, PostGIS event store, segment aggregation workers, routing graph service, alert fanout.
- Model training: a separate registry and evaluation pipeline; model versions are included in event metadata.
- Parking/ANPR (owned elsewhere): must publish ordinary `RoadEvent` records. Plate text must never be put in `attributes`; use a restricted, retention-controlled store.

## Delivery sequence

1. Freeze `v1` contract and add JSON Schema / OpenAPI generation in the backend.
2. Replace perception heuristics with a versioned YOLO/segmentation adapter evaluated per road class and weather/lighting slice.
3. Add an HMM/particle-filter map matcher backed by the road graph; preserve the simple matcher as a fallback.
4. Stream traffic aggregation through a durable queue, persist daily segment summaries, and fuse providers by provenance.
5. Feed road-condition and traffic snapshots into a production router; validate alert latency and safety policies end-to-end.
