from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from road_intelligence.contracts import (
    EventCategory,
    GeoPoint,
    RoadEvent,
    SourceType,
    VehicleObservation,
)
from road_intelligence.perception import Detection, PerceptionNormalizer
from road_intelligence.routing import RoadEdge, RouteResult, Router, SpeedAdvisory
from road_intelligence.sensor_fusion import GnssSample, ImuSample, SensorFusion
from road_intelligence.traffic import SegmentTrafficState, TrafficIntelligence

try:
    from .seed_data import (
        NODES,
        EdgeUnitSeed,
        NodeDef,
        ParkingSegmentSeed,
        SegmentDef,
        build_initial_traffic,
        build_seed_events,
        build_seed_fleet,
        build_seed_parking,
        build_segments,
        load_model_registry,
    )
except ImportError:
    from seed_data import (
        NODES,
        EdgeUnitSeed,
        NodeDef,
        ParkingSegmentSeed,
        SegmentDef,
        build_initial_traffic,
        build_seed_events,
        build_seed_fleet,
        build_seed_parking,
        build_segments,
        load_model_registry,
    )

PROHIBITED_ATTRIBUTE_KEYS = frozenset(
    {
        "plate_text",
        "license_plate",
        "raw_plate",
        "raw_image",
        "image_base64",
        "frame_base64",
        "driver_id",
        "phone",
        "email",
        "pii",
    }
)

ROAD_QUALITY_CATEGORIES = frozenset(
    {
        EventCategory.POTHOLE,
        EventCategory.CRACK,
        EventCategory.UNEVEN_SURFACE,
        EventCategory.SPEED_BREAKER,
    }
)

HAZARD_CATEGORIES = frozenset(
    {
        EventCategory.OBSTACLE,
        EventCategory.WATERLOGGING,
        EventCategory.CONSTRUCTION,
        EventCategory.INCIDENT,
        EventCategory.ROAD_CLOSURE,
    }
)


@dataclass
class EventRecord:
    event: RoadEvent
    workflow_status: str = "active"  # active | verified | resolved | dismissed
    confirmations: int = 0
    dismissals: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = self.event.to_dict()
        payload["workflow_status"] = self.workflow_status
        payload["confirmations"] = self.confirmations
        payload["dismissals"] = self.dismissals
        return payload


@dataclass
class SegmentState:
    definition: SegmentDef
    traffic: SegmentTrafficState
    observations: list[VehicleObservation] = field(default_factory=list)
    closed: bool = False
    manual_hazard_penalty: float = 0.0
    road_quality_penalty: float = 0.0
    hazard_penalty: float = 0.0
    congestion_penalty: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.definition.segment_id,
            "name": self.definition.name,
            "start": self.definition.start,
            "end": self.definition.end,
            "distance_km": self.definition.distance_km,
            "base_travel_minutes": self.definition.base_travel_minutes,
            "legal_speed_limit_kph": self.definition.legal_speed_limit_kph,
            "free_flow_speed_kph": self.definition.free_flow_speed_kph,
            "polyline": [[lat, lon] for lat, lon in self.definition.polyline],
            "closed": self.closed,
            "road_quality_penalty": round(self.road_quality_penalty, 2),
            "hazard_penalty": round(self.hazard_penalty, 2),
            "congestion_penalty": round(self.congestion_penalty, 2),
            "traffic": {
                "road_segment_id": self.traffic.road_segment_id,
                "mean_speed_kph": self.traffic.mean_speed_kph,
                "free_flow_speed_kph": self.traffic.free_flow_speed_kph,
                "vehicle_count": self.traffic.vehicle_count,
                "congestion_ratio": self.traffic.congestion_ratio,
                "is_congested": self.traffic.is_congested,
            },
        }


class RoadIntelligenceStore:
    """In-memory deterministic state store backed by `road_intelligence` core modules."""

    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.nodes: dict[str, NodeDef] = {node.id: node for node in NODES}
        segment_defs = build_segments()
        traffic_map = build_initial_traffic(segment_defs, now)

        self.segments: dict[str, SegmentState] = {}
        for seg_def in segment_defs:
            traffic_state, obs_list = traffic_map[seg_def.segment_id]
            self.segments[seg_def.segment_id] = SegmentState(
                definition=seg_def,
                traffic=traffic_state,
                observations=obs_list,
            )

        self.events: dict[str, EventRecord] = {}
        for spec in build_seed_events(segment_defs, traffic_map, now):
            self.events[spec.event.event_id] = EventRecord(
                event=spec.event,
                workflow_status=spec.workflow_status,
                confirmations=spec.confirmations,
                dismissals=spec.dismissals,
            )

        self.parking: dict[str, ParkingSegmentSeed] = {
            p.road_segment_id: p for p in build_seed_parking(now)
        }
        self.fleet: list[EdgeUnitSeed] = build_seed_fleet(now)
        self.model_registry: list[dict[str, Any]] = load_model_registry()
        self.normalizer = PerceptionNormalizer()
        self.traffic_intel = TrafficIntelligence()
        self._subscribers: set[asyncio.Queue[tuple[str, dict[str, Any]]]] = set()
        self.recompute_segment_penalties()

    # ------------------------------------------------------------------
    # SSE Pub/Sub
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[tuple[str, dict[str, Any]]]) -> None:
        self._subscribers.discard(queue)

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        dead: list[asyncio.Queue[tuple[str, dict[str, Any]]]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait((event_type, payload))
            except asyncio.QueueFull:
                dead.append(queue)
        for q in dead:
            self._subscribers.discard(q)

    # ------------------------------------------------------------------
    # Penalty Aggregation & Router Construction
    # ------------------------------------------------------------------

    @staticmethod
    def _severity_weight(attributes: dict[str, Any], default: float = 3.0) -> float:
        sev = str(attributes.get("severity", "medium")).lower()
        return {"low": 1.8, "medium": 3.5, "high": 6.5}.get(sev, default)

    def recompute_segment_penalties(self) -> None:
        for seg_state in self.segments.values():
            seg_state.road_quality_penalty = seg_state.definition.base_road_quality_penalty
            seg_state.hazard_penalty = seg_state.manual_hazard_penalty
            seg_state.congestion_penalty = round(seg_state.traffic.congestion_ratio * 8.0, 2)

        for rec in self.events.values():
            if rec.workflow_status in {"resolved", "dismissed"}:
                continue
            seg_id = rec.event.road_segment_id
            if not seg_id or seg_id not in self.segments:
                continue
            seg_state = self.segments[seg_id]
            weight = self._severity_weight(rec.event.attributes) * max(0.5, rec.event.confidence)
            if rec.event.category in ROAD_QUALITY_CATEGORIES:
                seg_state.road_quality_penalty += weight
            elif rec.event.category in HAZARD_CATEGORIES:
                seg_state.hazard_penalty += weight

    def build_router(self) -> Router:
        edges: list[RoadEdge] = []
        for seg_state in self.segments.values():
            if seg_state.closed:
                continue
            d = seg_state.definition
            congestion_factor = 1.0 + (seg_state.traffic.congestion_ratio * 0.35)
            effective_minutes = round(d.base_travel_minutes * congestion_factor, 2)
            # Bidirectional edges so navigation works in either direction
            for u, v in ((d.start, d.end), (d.end, d.start)):
                edges.append(
                    RoadEdge(
                        start=u,
                        end=v,
                        distance_km=d.distance_km,
                        travel_minutes=effective_minutes,
                        road_quality_penalty=round(seg_state.road_quality_penalty, 2),
                        hazard_penalty=round(seg_state.hazard_penalty, 2),
                        congestion_penalty=round(seg_state.congestion_penalty, 2),
                        legal_speed_limit_kph=d.legal_speed_limit_kph,
                    )
                )
        return Router(edges)

    def _find_segment_between(self, a: str, b: str) -> SegmentState | None:
        for seg_state in self.segments.values():
            d = seg_state.definition
            if (d.start == a and d.end == b) or (d.end == a and d.start == b):
                return seg_state
        return None

    # ------------------------------------------------------------------
    # Routing & Speed Advisories
    # ------------------------------------------------------------------

    def compare_routes(self, origin: str, destination: str) -> dict[str, Any]:
        if origin not in self.nodes or destination not in self.nodes:
            raise ValueError("unknown origin or destination node")
        if origin == destination:
            raise ValueError("origin and destination must be different")

        router = self.build_router()
        profiles = ("balanced", "safest", "smoothest", "fastest")
        results: list[dict[str, Any]] = []

        for profile in profiles:
            res: RouteResult = router.route(origin, destination, profile=profile)
            segment_ids: list[str] = []
            polyline: list[list[float]] = []
            total_quality_pen = 0.0
            total_hazard_pen = 0.0
            legal_limits: list[int] = []

            for i in range(len(res.nodes) - 1):
                u, v = res.nodes[i], res.nodes[i + 1]
                seg = self._find_segment_between(u, v)
                if seg is None:
                    continue
                segment_ids.append(seg.definition.segment_id)
                total_quality_pen += seg.road_quality_penalty
                total_hazard_pen += seg.hazard_penalty
                legal_limits.append(seg.definition.legal_speed_limit_kph)

                pts = list(seg.definition.polyline)
                if seg.definition.end == u and seg.definition.start == v:
                    pts.reverse()
                for idx, (lat, lon) in enumerate(pts):
                    if i > 0 and idx == 0:
                        continue
                    polyline.append([lat, lon])

            route_events = [
                rec.to_dict()
                for rec in self.events.values()
                if rec.workflow_status in {"active", "verified"}
                and rec.event.road_segment_id in segment_ids
            ]
            hazard_count = len([e for e in route_events if e["category"] != EventCategory.SPEED_LIMIT_SIGN.value])
            road_quality_score = max(18, min(99, round(100 - total_quality_pen * 2.2 - total_hazard_pen * 1.4)))

            explanation = self._explain_route(profile, res, hazard_count, road_quality_score)
            results.append(
                {
                    "profile": profile,
                    "nodes": list(res.nodes),
                    "node_names": [self.nodes[n].name for n in res.nodes],
                    "segment_ids": segment_ids,
                    "polyline": polyline,
                    "score": res.score,
                    "distance_km": res.distance_km,
                    "travel_minutes": res.travel_minutes,
                    "road_quality_score": road_quality_score,
                    "hazard_count": hazard_count,
                    "default_legal_speed_limit_kph": min(legal_limits) if legal_limits else 40,
                    "events": route_events,
                    "explanation": explanation,
                }
            )

        return {
            "origin": origin,
            "destination": destination,
            "routes": results,
        }

    @staticmethod
    def _explain_route(profile: str, res: RouteResult, hazard_count: int, quality_score: int) -> str:
        if profile == "fastest":
            return f"Shortest ETA ({res.travel_minutes} min) across {hazard_count} active road notices."
        if profile == "safest":
            return f"Avoids high-severity hazards ({hazard_count} notices, quality {quality_score}/100)."
        if profile == "smoothest":
            return f"Minimizes potholes and surface roughness (surface score {quality_score}/100)."
        return f"Balances {res.travel_minutes} min travel time with surface quality ({quality_score}/100)."

    @staticmethod
    def compute_advisory(
        legal_speed_limit_kph: int | None,
        hazard: str | None,
        distance_to_hazard_m: float | None,
    ) -> SpeedAdvisory:
        return Router.speed_advisory(legal_speed_limit_kph, hazard, distance_to_hazard_m)

    # ------------------------------------------------------------------
    # Perception + Sensor Fusion Ingestion
    # ------------------------------------------------------------------

    def ingest_perception(
        self,
        *,
        label: str,
        confidence: float,
        bbox_area_ratio: float,
        model_version: str,
        frame_timestamp: datetime,
        gnss_samples: list[GnssSample],
        imu_sample: ImuSample | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw_attrs = dict(attributes or {})
        found_pii = sorted(k for k in raw_attrs if k.lower() in PROHIBITED_ATTRIBUTE_KEYS)
        if found_pii:
            raise ValueError(
                f"Privacy contract violation: prohibited keys in RoadEvent.attributes: {', '.join(found_pii)}"
            )

        candidate_segments: dict[str, GeoPoint] = {}
        for seg_id, seg_state in self.segments.items():
            mid = seg_state.definition.polyline[min(1, len(seg_state.definition.polyline) - 1)]
            candidate_segments[seg_id] = GeoPoint(mid[0], mid[1])

        fusion = SensorFusion(gnss_samples, max_alignment_ms=750)
        estimate = fusion.locate(frame_timestamp, candidate_segments=candidate_segments)

        detection = Detection(
            label=label,
            confidence=confidence,
            frame_timestamp=frame_timestamp,
            bbox_area_ratio=bbox_area_ratio,
            model_version=model_version,
        )
        event = self.normalizer.normalize(
            detection,
            estimate.location,
            round(estimate.accuracy_m, 2),
            road_segment_id=estimate.road_segment_id,
        )
        if event is None:
            raise ValueError(
                f"Detection rejected by PerceptionNormalizer (unsupported label '{label}' or confidence {confidence:.2f} < 0.45)"
            )

        harsh_brake = SensorFusion.harsh_braking(imu_sample) if imu_sample is not None else False
        merged_attrs = {**event.attributes, **raw_attrs}
        if harsh_brake and imu_sample is not None:
            merged_attrs["imu_harsh_braking"] = True
            merged_attrs["longitudinal_accel_mps2"] = imu_sample.longitudinal_accel_mps2

        enriched_event = RoadEvent(
            event_id=event.event_id,
            category=event.category,
            source_type=event.source_type,
            observed_at=event.observed_at,
            location=event.location,
            confidence=event.confidence,
            location_accuracy_m=event.location_accuracy_m,
            road_segment_id=event.road_segment_id,
            attributes=merged_attrs,
            schema_version=event.schema_version,
        )

        record = EventRecord(event=enriched_event, workflow_status="active", confirmations=1)
        self.events[enriched_event.event_id] = record
        self.recompute_segment_penalties()
        payload = record.to_dict()
        self._publish("event_created", payload)

        return {
            "event": payload,
            "fusion": {
                "age_ms": round(estimate.age_ms, 1),
                "accuracy_m": round(estimate.accuracy_m, 2),
                "speed_kph": round(estimate.speed_kph, 1),
                "road_segment_id": estimate.road_segment_id,
                "harsh_braking_detected": harsh_brake,
            },
        }

    # ------------------------------------------------------------------
    # Driver Feedback & Admin Moderation
    # ------------------------------------------------------------------

    def apply_driver_feedback(self, event_id: str, action: str) -> dict[str, Any]:
        rec = self.events.get(event_id)
        if rec is None:
            raise KeyError(event_id)
        if action == "confirm":
            rec.confirmations += 1
            if rec.workflow_status == "active" and rec.confirmations >= 3:
                rec.workflow_status = "verified"
        elif action == "cleared":
            rec.dismissals += 1
            if rec.dismissals >= 2:
                rec.workflow_status = "resolved"
        else:
            raise ValueError("action must be 'confirm' or 'cleared'")
        self.recompute_segment_penalties()
        payload = rec.to_dict()
        self._publish("event_updated", payload)
        return payload

    def moderate_event(self, event_id: str, workflow_status: str, severity: str | None = None) -> dict[str, Any]:
        rec = self.events.get(event_id)
        if rec is None:
            raise KeyError(event_id)
        if workflow_status not in {"active", "verified", "resolved", "dismissed"}:
            raise ValueError("invalid workflow_status")
        rec.workflow_status = workflow_status
        if severity in {"low", "medium", "high"}:
            attrs = dict(rec.event.attributes)
            attrs["severity"] = severity
            rec.event = RoadEvent(
                event_id=rec.event.event_id,
                category=rec.event.category,
                source_type=rec.event.source_type,
                observed_at=rec.event.observed_at,
                location=rec.event.location,
                confidence=rec.event.confidence,
                location_accuracy_m=rec.event.location_accuracy_m,
                road_segment_id=rec.event.road_segment_id,
                attributes=attrs,
                schema_version=rec.event.schema_version,
            )
        self.recompute_segment_penalties()
        payload = rec.to_dict()
        self._publish("event_updated", payload)
        return payload

    def update_segment(
        self,
        segment_id: str,
        *,
        closed: bool | None = None,
        extra_hazard_penalty: float | None = None,
        mean_speed_kph: float | None = None,
        vehicle_count: int = 12,
    ) -> dict[str, Any]:
        seg = self.segments.get(segment_id)
        if seg is None:
            raise KeyError(segment_id)

        if closed is not None:
            seg.closed = closed
        if extra_hazard_penalty is not None:
            seg.manual_hazard_penalty = max(0.0, extra_hazard_penalty)

        emitted_congestion: dict[str, Any] | None = None
        if mean_speed_kph is not None:
            now = datetime.now(timezone.utc)
            obs = VehicleObservation(
                road_segment_id=segment_id,
                observed_at=now,
                speed_kph=mean_speed_kph,
                vehicle_count=max(1, vehicle_count),
                source_type=SourceType.TELEMETRY_AGGREGATED,
            )
            seg.observations.append(obs)
            seg.traffic = self.traffic_intel.summarize(
                seg.observations[-5:], seg.definition.free_flow_speed_kph
            )
            mid = seg.definition.polyline[min(1, len(seg.definition.polyline) - 1)]
            cong_evt = self.traffic_intel.congestion_event(seg.traffic, GeoPoint(mid[0], mid[1]), now)
            if cong_evt is not None:
                rec = EventRecord(event=cong_evt, workflow_status="active", confirmations=1)
                self.events[cong_evt.event_id] = rec
                emitted_congestion = rec.to_dict()
                self._publish("event_created", emitted_congestion)

        self.recompute_segment_penalties()
        seg_payload = seg.to_dict()
        self._publish("segment_updated", seg_payload)
        return {"segment": seg_payload, "emitted_congestion_event": emitted_congestion}

    # ------------------------------------------------------------------
    # Read Helpers
    # ------------------------------------------------------------------

    def list_events(
        self,
        *,
        category: str | None = None,
        source_type: str | None = None,
        status: str | None = None,
        min_confidence: float | None = None,
        segment_id: str | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[EventRecord] = []
        for rec in self.events.values():
            if category and rec.event.category.value != category:
                continue
            if source_type and rec.event.source_type.value != source_type:
                continue
            if status and rec.workflow_status != status:
                continue
            if min_confidence is not None and rec.event.confidence < min_confidence:
                continue
            if segment_id and rec.event.road_segment_id != segment_id:
                continue
            rows.append(rec)
        rows.sort(key=lambda r: r.event.observed_at, reverse=True)
        return [r.to_dict() for r in rows]

    def list_network(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "area": n.area,
                    "latitude": n.latitude,
                    "longitude": n.longitude,
                }
                for n in self.nodes.values()
            ],
            "segments": [s.to_dict() for s in self.segments.values()],
        }

    def list_parking(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for p in self.parking.values():
            available = max(0, p.total_spaces_estimated - p.occupied_spaces)
            rows.append(
                {
                    "road_segment_id": p.road_segment_id,
                    "segment_name": p.segment_name,
                    "area": p.area,
                    "total_spaces_estimated": p.total_spaces_estimated,
                    "occupied_spaces": p.occupied_spaces,
                    "available_spaces": available,
                    "occupancy_rate": round(p.occupancy_rate, 3),
                    "confidence": round(p.confidence, 2),
                    "history_window_size": p.history_window_size,
                    "last_observed": p.last_observed.astimezone(timezone.utc).isoformat(),
                    "center": {"latitude": p.center.latitude, "longitude": p.center.longitude},
                    "polyline": [[lat, lon] for lat, lon in p.polyline],
                    "privacy_masked": p.privacy_masked,
                }
            )
        rows.sort(key=lambda item: item["available_spaces"], reverse=True)
        return rows

    def get_fleet_and_compliance(self) -> dict[str, Any]:
        pii_violations = 0
        for rec in self.events.values():
            if any(k.lower() in PROHIBITED_ATTRIBUTE_KEYS for k in rec.event.attributes):
                pii_violations += 1

        return {
            "units": [
                {
                    "unit_id": u.unit_id,
                    "vehicle_label": u.vehicle_label,
                    "corridor": u.corridor,
                    "status": u.status,
                    "latitude": u.latitude,
                    "longitude": u.longitude,
                    "gnss_age_ms": u.gnss_age_ms,
                    "gnss_max_alignment_ms": 750,
                    "gnss_accuracy_m": u.gnss_accuracy_m,
                    "imu_harsh_brakes_1h": u.imu_harsh_brakes_1h,
                    "model_version": u.model_version,
                    "fps": u.fps,
                    "parking_every_n": u.parking_every_n,
                    "anpr_every_n": u.anpr_every_n,
                    "plate_blur_enabled": u.plate_blur_enabled,
                    "buffer_queue_depth": u.buffer_queue_depth,
                    "last_heartbeat": u.last_heartbeat.astimezone(timezone.utc).isoformat(),
                }
                for u in self.fleet
            ],
            "models": self.model_registry,
            "privacy": {
                "plate_mask_blur_kernel_px": 51,
                "retention_plain_hours": 24,
                "retention_flagged_days": 7,
                "plate_hash_algorithm": "HMAC-Salted SHA-256",
                "prohibited_attributes_detected": pii_violations,
                "gnss_max_alignment_ms": 750,
                "imu_harsh_braking_threshold_mps2": -3.0,
            },
        }

    # ------------------------------------------------------------------
    # QGIS / OGC GeoJSON & Project Export
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in attrs.items() if k.lower() not in PROHIBITED_ATTRIBUTE_KEYS}

    def events_geojson(self) -> dict[str, Any]:
        features: list[dict[str, Any]] = []
        for rec in self.events.values():
            evt = rec.event
            features.append(
                {
                    "type": "Feature",
                    "id": evt.event_id,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [evt.location.longitude, evt.location.latitude],
                    },
                    "properties": {
                        "event_id": evt.event_id,
                        "schema_version": evt.schema_version,
                        "category": evt.category.value,
                        "source_type": evt.source_type.value,
                        "confidence": evt.confidence,
                        "location_accuracy_m": evt.location_accuracy_m,
                        "road_segment_id": evt.road_segment_id,
                        "workflow_status": rec.workflow_status,
                        "confirmations": rec.confirmations,
                        "dismissals": rec.dismissals,
                        "observed_at": evt.observed_at.astimezone(timezone.utc).isoformat(),
                        "attributes": self._sanitize_attributes(evt.attributes),
                    },
                }
            )
        return {"type": "FeatureCollection", "name": "roadsense_events", "features": features}

    def segments_geojson(self) -> dict[str, Any]:
        features: list[dict[str, Any]] = []
        for seg in self.segments.values():
            d = seg.definition
            features.append(
                {
                    "type": "Feature",
                    "id": d.segment_id,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[lon, lat] for lat, lon in d.polyline],
                    },
                    "properties": {
                        "segment_id": d.segment_id,
                        "name": d.name,
                        "legal_speed_limit_kph": d.legal_speed_limit_kph,
                        "free_flow_speed_kph": d.free_flow_speed_kph,
                        "mean_speed_kph": seg.traffic.mean_speed_kph,
                        "congestion_ratio": seg.traffic.congestion_ratio,
                        "is_congested": seg.traffic.is_congested,
                        "closed": seg.closed,
                        "road_quality_penalty": round(seg.road_quality_penalty, 2),
                        "hazard_penalty": round(seg.hazard_penalty, 2),
                    },
                }
            )
        return {"type": "FeatureCollection", "name": "roadsense_segments", "features": features}

    def parking_geojson(self) -> dict[str, Any]:
        features: list[dict[str, Any]] = []
        for p in self.parking.values():
            available = max(0, p.total_spaces_estimated - p.occupied_spaces)
            features.append(
                {
                    "type": "Feature",
                    "id": p.road_segment_id,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[lon, lat] for lat, lon in p.polyline],
                    },
                    "properties": {
                        "road_segment_id": p.road_segment_id,
                        "segment_name": p.segment_name,
                        "area": p.area,
                        "available_spaces": available,
                        "occupied_spaces": p.occupied_spaces,
                        "total_spaces_estimated": p.total_spaces_estimated,
                        "occupancy_rate": round(p.occupancy_rate, 3),
                        "confidence": round(p.confidence, 2),
                        "privacy_masked": p.privacy_masked,
                    },
                }
            )
        return {"type": "FeatureCollection", "name": "roadsense_parking", "features": features}

    @staticmethod
    def build_qgis_project_xml(base_url: str) -> str:
        root = base_url.rstrip("/")
        events_src = f"{root}/api/gis/events.geojson"
        segments_src = f"{root}/api/gis/segments.geojson"
        parking_src = f"{root}/api/gis/parking.geojson"
        return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis projectname="RoadSense Bengaluru Intelligence" version="3.34.0-Prizren">
  <title>RoadSense Bengaluru Intelligence</title>
  <projectCrs>
    <spatialrefsys nativeFormat="Wkt">
      <authid>EPSG:3857</authid>
    </spatialrefsys>
  </projectCrs>
  <mapcanvas name="theMapCanvas">
    <extent>
      <xmin>8634000</xmin>
      <ymin>1451000</ymin>
      <xmax>8646000</xmax>
      <ymax>1459000</ymax>
    </extent>
    <destinationsrs>
      <spatialrefsys><authid>EPSG:3857</authid></spatialrefsys>
    </destinationsrs>
  </mapcanvas>
  <layer-tree-group>
    <layer-tree-layer id="roadsense_events" name="RoadEvents v1 (Live GeoJSON)" checked="Qt::Checked" source="{events_src}"/>
    <layer-tree-layer id="roadsense_parking" name="Parking Corridors (Anonymized GeoJSON)" checked="Qt::Checked" source="{parking_src}"/>
    <layer-tree-layer id="roadsense_segments" name="Road Segments &amp; Traffic (GeoJSON)" checked="Qt::Checked" source="{segments_src}"/>
    <layer-tree-layer id="osm_xyz" name="OpenStreetMap" checked="Qt::Checked" source="type=xyz&amp;url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&amp;zmax=19&amp;zmin=0"/>
  </layer-tree-group>
  <projectlayers>
    <maplayer type="vector" geometry="Point">
      <id>roadsense_events</id>
      <layername>RoadEvents v1 (Live GeoJSON)</layername>
      <datasource>{events_src}</datasource>
      <provider encoding="UTF-8">ogr</provider>
      <srs><spatialrefsys><authid>EPSG:4326</authid></spatialrefsys></srs>
    </maplayer>
    <maplayer type="vector" geometry="Line">
      <id>roadsense_parking</id>
      <layername>Parking Corridors (Anonymized GeoJSON)</layername>
      <datasource>{parking_src}</datasource>
      <provider encoding="UTF-8">ogr</provider>
      <srs><spatialrefsys><authid>EPSG:4326</authid></spatialrefsys></srs>
    </maplayer>
    <maplayer type="vector" geometry="Line">
      <id>roadsense_segments</id>
      <layername>Road Segments &amp; Traffic (GeoJSON)</layername>
      <datasource>{segments_src}</datasource>
      <provider encoding="UTF-8">ogr</provider>
      <srs><spatialrefsys><authid>EPSG:4326</authid></spatialrefsys></srs>
    </maplayer>
    <maplayer type="raster">
      <id>osm_xyz</id>
      <layername>OpenStreetMap</layername>
      <datasource>type=xyz&amp;url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&amp;zmax=19&amp;zmin=0</datasource>
      <provider>wms</provider>
      <srs><spatialrefsys><authid>EPSG:3857</authid></spatialrefsys></srs>
    </maplayer>
  </projectlayers>
</qgis>
"""


store = RoadIntelligenceStore()

