from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from road_intelligence.contracts import (
    EventCategory,
    GeoPoint,
    RoadEvent,
    SourceType,
    VehicleObservation,
)
from road_intelligence.traffic import SegmentTrafficState, TrafficIntelligence


@dataclass(frozen=True)
class NodeDef:
    id: str
    name: str
    area: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class SegmentDef:
    segment_id: str
    name: str
    start: str
    end: str
    distance_km: float
    base_travel_minutes: float
    legal_speed_limit_kph: int
    free_flow_speed_kph: float
    base_road_quality_penalty: float
    polyline: tuple[tuple[float, float], ...]


@dataclass
class SeedEventSpec:
    event: RoadEvent
    workflow_status: str = "active"
    confirmations: int = 0
    dismissals: int = 0


@dataclass
class ParkingSegmentSeed:
    road_segment_id: str
    segment_name: str
    area: str
    total_spaces_estimated: int
    occupied_spaces: int
    occupancy_rate: float
    confidence: float
    history_window_size: int
    last_observed: datetime
    center: GeoPoint
    polyline: tuple[tuple[float, float], ...]
    privacy_masked: bool = True


@dataclass
class EdgeUnitSeed:
    unit_id: str
    vehicle_label: str
    corridor: str
    status: str
    latitude: float
    longitude: float
    gnss_age_ms: float
    gnss_accuracy_m: float
    imu_harsh_brakes_1h: int
    model_version: str
    fps: float
    parking_every_n: int
    anpr_every_n: int
    plate_blur_enabled: bool
    buffer_queue_depth: int
    last_heartbeat: datetime


NODES: tuple[NodeDef, ...] = (
    NodeDef("cubbon", "Cubbon Park Gate", "Central Business District", 12.9763, 77.5929),
    NodeDef("mg_road", "MG Road Metro", "MG Road", 12.9756, 77.6066),
    NodeDef("trinity", "Trinity Circle", "Halasuru Border", 12.9730, 77.6170),
    NodeDef("ulsoor", "Ulsoor Lake Rd", "Halasuru", 12.9822, 77.6208),
    NodeDef("indiranagar", "100ft Rd Junction", "Indiranagar", 12.9784, 77.6408),
    NodeDef("domlur", "Domlur Flyover", "Domlur", 12.9610, 77.6387),
    NodeDef("richmond", "Richmond Circle", "Richmond Town", 12.9665, 77.5985),
    NodeDef("shanthinagar", "Shanthinagar TTMC", "Shanthinagar", 12.9548, 77.5966),
    NodeDef("ejipura", "Ejipura Signal", "Inner Ring Rd", 12.9438, 77.6226),
    NodeDef("koramangala", "Koramangala Sony World", "Koramangala 4th Block", 12.9352, 77.6245),
)

# Undirected corridor definitions converted to bidirectional directed segments
_CORRIDORS: tuple[dict[str, Any], ...] = (
    # Corridor A (Fastest direct southern arterial with active road defects & congestion)
    {
        "id": "osm-way-cubbon-richmond",
        "name": "Kasturba - Richmond Rd",
        "start": "cubbon",
        "end": "richmond",
        "distance_km": 1.2,
        "minutes": 2.4,
        "legal": 50,
        "free_flow": 50.0,
        "base_quality": 1.0,
        "polyline": ((12.9763, 77.5929), (12.9712, 77.5961), (12.9665, 77.5985)),
    },
    {
        "id": "osm-way-richmond-shanthi",
        "name": "KH Double Road",
        "start": "richmond",
        "end": "shanthinagar",
        "distance_km": 1.4,
        "minutes": 2.7,
        "legal": 40,
        "free_flow": 45.0,
        "base_quality": 1.5,
        "polyline": ((12.9665, 77.5985), (12.9609, 77.5974), (12.9548, 77.5966)),
    },
    {
        "id": "osm-way-shanthi-ejipura",
        "name": "Koramangala Inner Link",
        "start": "shanthinagar",
        "end": "ejipura",
        "distance_km": 1.8,
        "minutes": 3.1,
        "legal": 40,
        "free_flow": 45.0,
        "base_quality": 2.0,
        "polyline": ((12.9548, 77.5966), (12.9495, 77.6095), (12.9438, 77.6226)),
    },
    {
        "id": "osm-way-ejipura-kora",
        "name": "100ft Rd Ejipura-Kora",
        "start": "ejipura",
        "end": "koramangala",
        "distance_km": 1.4,
        "minutes": 2.5,
        "legal": 50,
        "free_flow": 50.0,
        "base_quality": 1.0,
        "polyline": ((12.9438, 77.6226), (12.9396, 77.6238), (12.9352, 77.6245)),
    },
    # Corridor B (Balanced eastern mid-corridor)
    {
        "id": "osm-way-cubbon-mg",
        "name": "MG Road Central",
        "start": "cubbon",
        "end": "mg_road",
        "distance_km": 1.4,
        "minutes": 3.0,
        "legal": 50,
        "free_flow": 50.0,
        "base_quality": 0.5,
        "polyline": ((12.9763, 77.5929), (12.9760, 77.5998), (12.9756, 77.6066)),
    },
    {
        "id": "osm-way-mg-trinity",
        "name": "MG Road - Trinity",
        "start": "mg_road",
        "end": "trinity",
        "distance_km": 1.2,
        "minutes": 2.6,
        "legal": 50,
        "free_flow": 50.0,
        "base_quality": 0.5,
        "polyline": ((12.9756, 77.6066), (12.9743, 77.6119), (12.9730, 77.6170)),
    },
    {
        "id": "osm-way-trinity-ejipura",
        "name": "Victoria - Ejipura Rd",
        "start": "trinity",
        "end": "ejipura",
        "distance_km": 2.4,
        "minutes": 4.2,
        "legal": 40,
        "free_flow": 45.0,
        "base_quality": 1.0,
        "polyline": ((12.9730, 77.6170), (12.9585, 77.6198), (12.9438, 77.6226)),
    },
    # Corridor C (Safest & Smoothest outer boulevard)
    {
        "id": "osm-way-mg-ulsoor",
        "name": "Dickenson - Ulsoor Rd",
        "start": "mg_road",
        "end": "ulsoor",
        "distance_km": 1.8,
        "minutes": 3.8,
        "legal": 50,
        "free_flow": 50.0,
        "base_quality": 0.4,
        "polyline": ((12.9756, 77.6066), (12.9795, 77.6135), (12.9822, 77.6208)),
    },
    {
        "id": "osm-way-ulsoor-indira",
        "name": "CMH Road Indiranagar",
        "start": "ulsoor",
        "end": "indiranagar",
        "distance_km": 2.3,
        "minutes": 4.2,
        "legal": 50,
        "free_flow": 55.0,
        "base_quality": 0.4,
        "polyline": ((12.9822, 77.6208), (12.9806, 77.6308), (12.9784, 77.6408)),
    },
    {
        "id": "osm-way-indira-domlur",
        "name": "100ft Rd Indiranagar-Domlur",
        "start": "indiranagar",
        "end": "domlur",
        "distance_km": 2.0,
        "minutes": 3.6,
        "legal": 60,
        "free_flow": 60.0,
        "base_quality": 0.3,
        "polyline": ((12.9784, 77.6408), (12.9698, 77.6399), (12.9610, 77.6387)),
    },
    {
        "id": "osm-way-domlur-kora",
        "name": "Inner Ring Rd Domlur-Kora",
        "start": "domlur",
        "end": "koramangala",
        "distance_km": 2.2,
        "minutes": 3.9,
        "legal": 60,
        "free_flow": 60.0,
        "base_quality": 0.3,
        "polyline": ((12.9610, 77.6387), (12.9482, 77.6320), (12.9352, 77.6245)),
    },
    # Cross connections for richer routing network
    {
        "id": "osm-way-mg-richmond",
        "name": "Brigade - Residency Rd",
        "start": "mg_road",
        "end": "richmond",
        "distance_km": 1.3,
        "minutes": 3.1,
        "legal": 40,
        "free_flow": 45.0,
        "base_quality": 0.8,
        "polyline": ((12.9756, 77.6066), (12.9708, 77.6024), (12.9665, 77.5985)),
    },
    {
        "id": "osm-way-richmond-domlur",
        "name": "Langford - Domlur Link",
        "start": "richmond",
        "end": "domlur",
        "distance_km": 4.5,
        "minutes": 9.8,
        "legal": 50,
        "free_flow": 55.0,
        "base_quality": 1.0,
        "polyline": ((12.9665, 77.5985), (12.9642, 77.6195), (12.9610, 77.6387)),
    },
    {
        "id": "osm-way-trinity-domlur",
        "name": "Old Airport Rd (Trinity-Domlur)",
        "start": "trinity",
        "end": "domlur",
        "distance_km": 2.7,
        "minutes": 5.5,
        "legal": 50,
        "free_flow": 55.0,
        "base_quality": 0.9,
        "polyline": ((12.9730, 77.6170), (12.9672, 77.6281), (12.9610, 77.6387)),
    },
)


def build_segments() -> list[SegmentDef]:
    segments: list[SegmentDef] = []
    for item in _CORRIDORS:
        poly = item["polyline"]
        segments.append(
            SegmentDef(
                segment_id=item["id"],
                name=item["name"],
                start=item["start"],
                end=item["end"],
                distance_km=item["distance_km"],
                base_travel_minutes=item["minutes"],
                legal_speed_limit_kph=item["legal"],
                free_flow_speed_kph=item["free_flow"],
                base_road_quality_penalty=item["base_quality"],
                polyline=poly,
            )
        )
    return segments


def build_initial_traffic(segments: list[SegmentDef], now: datetime) -> dict[str, tuple[SegmentTrafficState, list[VehicleObservation]]]:
    intel = TrafficIntelligence()
    # Deterministic realistic speed profiles per segment
    speed_overrides = {
        "osm-way-cubbon-richmond": (22.0, 24),   # congested
        "osm-way-richmond-shanthi": (19.0, 31),  # congested
        "osm-way-shanthi-ejipura": (23.0, 19),   # congested
        "osm-way-ejipura-kora": (29.0, 15),      # moderate
        "osm-way-cubbon-mg": (38.0, 14),         # smooth
        "osm-way-mg-trinity": (36.0, 18),        # moderate
        "osm-way-trinity-ejipura": (31.0, 16),   # moderate
        "osm-way-mg-ulsoor": (44.0, 11),         # free-flowing
        "osm-way-ulsoor-indira": (47.0, 13),     # free-flowing
        "osm-way-indira-domlur": (52.0, 16),     # free-flowing
        "osm-way-domlur-kora": (50.0, 20),       # free-flowing
        "osm-way-mg-richmond": (28.0, 12),       # moderate
        "osm-way-richmond-domlur": (42.0, 10),   # smooth
        "osm-way-trinity-domlur": (34.0, 21),    # moderate
    }
    traffic_map: dict[str, tuple[SegmentTrafficState, list[VehicleObservation]]] = {}
    for seg in segments:
        mean_kph, count = speed_overrides.get(seg.segment_id, (seg.free_flow_speed_kph * 0.8, 10))
        obs = [
            VehicleObservation(
                road_segment_id=seg.segment_id,
                observed_at=now - timedelta(minutes=2),
                speed_kph=mean_kph,
                vehicle_count=count,
                source_type=SourceType.TELEMETRY_AGGREGATED,
            )
        ]
        state = intel.summarize(obs, seg.free_flow_speed_kph)
        traffic_map[seg.segment_id] = (state, obs)
    return traffic_map


def build_seed_events(
    segments: list[SegmentDef],
    traffic_map: dict[str, tuple[SegmentTrafficState, list[VehicleObservation]]],
    now: datetime,
) -> list[SeedEventSpec]:
    seg_by_id = {s.segment_id: s for s in segments}
    intel = TrafficIntelligence()

    def mid_point(seg_id: str, idx: int = 1) -> GeoPoint:
        poly = seg_by_id[seg_id].polyline
        lat, lon = poly[min(idx, len(poly) - 1)]
        return GeoPoint(lat, lon)

    specs: list[SeedEventSpec] = [
        # Corridor A heavy hazards (gives high road_quality & hazard penalty so safest/smoothest avoid it)
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_pothole_01",
                category=EventCategory.POTHOLE,
                source_type=SourceType.CAMERA_OBSERVED,
                observed_at=now - timedelta(minutes=6),
                location=mid_point("osm-way-cubbon-richmond"),
                confidence=0.92,
                location_accuracy_m=5.4,
                road_segment_id="osm-way-cubbon-richmond",
                attributes={"severity": "high", "model_version": "yolo11n-road-beta", "lane": "left", "depth_est": "deep"},
            ),
            workflow_status="verified",
            confirmations=7,
        ),
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_water_02",
                category=EventCategory.WATERLOGGING,
                source_type=SourceType.CAMERA_OBSERVED,
                observed_at=now - timedelta(minutes=11),
                location=GeoPoint(12.9632, 77.5979),
                confidence=0.87,
                location_accuracy_m=7.8,
                road_segment_id="osm-way-richmond-shanthi",
                attributes={"severity": "high", "model_version": "yolo11n-road-beta", "standing_water_m": 18},
            ),
            workflow_status="verified",
            confirmations=5,
        ),
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_pothole_03",
                category=EventCategory.POTHOLE,
                source_type=SourceType.SENSOR_OBSERVED,
                observed_at=now - timedelta(minutes=15),
                location=GeoPoint(12.9588, 77.5970),
                confidence=0.81,
                location_accuracy_m=9.2,
                road_segment_id="osm-way-richmond-shanthi",
                attributes={"severity": "high", "imu_vertical_spike_g": 2.4, "sensor_type": "imu_z_axis"},
            ),
            workflow_status="active",
            confirmations=3,
        ),
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_constr_04",
                category=EventCategory.CONSTRUCTION,
                source_type=SourceType.EXTERNAL_PROVIDER,
                observed_at=now - timedelta(minutes=28),
                location=mid_point("osm-way-shanthi-ejipura"),
                confidence=0.89,
                location_accuracy_m=18.0,
                road_segment_id="osm-way-shanthi-ejipura",
                attributes={"severity": "high", "provider": "bengaluru_traffic_feed", "lane_reduction": "2_to_1"},
            ),
            workflow_status="verified",
            confirmations=9,
        ),
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_uneven_05",
                category=EventCategory.UNEVEN_SURFACE,
                source_type=SourceType.SENSOR_OBSERVED,
                observed_at=now - timedelta(minutes=19),
                location=GeoPoint(12.9472, 77.6145),
                confidence=0.77,
                location_accuracy_m=11.0,
                road_segment_id="osm-way-shanthi-ejipura",
                attributes={"severity": "medium", "roughness_iri": 6.8},
            ),
            workflow_status="active",
            confirmations=2,
        ),
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_breaker_06",
                category=EventCategory.SPEED_BREAKER,
                source_type=SourceType.CAMERA_OBSERVED,
                observed_at=now - timedelta(minutes=4),
                location=mid_point("osm-way-ejipura-kora"),
                confidence=0.94,
                location_accuracy_m=4.6,
                road_segment_id="osm-way-ejipura-kora",
                attributes={"severity": "medium", "model_version": "yolo11n-road-beta", "unmarked": True},
            ),
            workflow_status="verified",
            confirmations=12,
        ),
        # Corridor B moderate events
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_crack_07",
                category=EventCategory.CRACK,
                source_type=SourceType.CAMERA_OBSERVED,
                observed_at=now - timedelta(minutes=22),
                location=mid_point("osm-way-trinity-ejipura"),
                confidence=0.73,
                location_accuracy_m=8.0,
                road_segment_id="osm-way-trinity-ejipura",
                attributes={"severity": "medium", "model_version": "yolo11n-road-beta"},
            ),
            workflow_status="active",
            confirmations=1,
        ),
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_obstacle_08",
                category=EventCategory.OBSTACLE,
                source_type=SourceType.CAMERA_OBSERVED,
                observed_at=now - timedelta(minutes=8),
                location=GeoPoint(12.9522, 77.6210),
                confidence=0.69,
                location_accuracy_m=6.5,
                road_segment_id="osm-way-trinity-ejipura",
                attributes={"severity": "medium", "model_version": "yolov8n.pt", "object_class": "stalled_auto"},
            ),
            workflow_status="active",
            confirmations=2,
        ),
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_sign_09",
                category=EventCategory.SPEED_LIMIT_SIGN,
                source_type=SourceType.CAMERA_OBSERVED,
                observed_at=now - timedelta(minutes=42),
                location=mid_point("osm-way-mg-trinity"),
                confidence=0.95,
                location_accuracy_m=4.2,
                road_segment_id="osm-way-mg-trinity",
                attributes={"severity": "low", "sign_value_kph": 50, "model_version": "rdd2022-yolov8s-best.pt"},
            ),
            workflow_status="verified",
            confirmations=6,
        ),
        # Cross-corridor incident & low-confidence event for triage
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_incident_10",
                category=EventCategory.INCIDENT,
                source_type=SourceType.EXTERNAL_PROVIDER,
                observed_at=now - timedelta(minutes=9),
                location=mid_point("osm-way-trinity-domlur"),
                confidence=0.84,
                location_accuracy_m=22.0,
                road_segment_id="osm-way-trinity-domlur",
                attributes={"severity": "medium", "provider": "municipal_dispatch", "description": "Minor fender stall"},
            ),
            workflow_status="active",
            confirmations=4,
        ),
        SeedEventSpec(
            RoadEvent(
                event_id="evt_bng_pothole_11",
                category=EventCategory.POTHOLE,
                source_type=SourceType.CAMERA_OBSERVED,
                observed_at=now - timedelta(minutes=3),
                location=mid_point("osm-way-mg-richmond"),
                confidence=0.58,
                location_accuracy_m=12.4,
                road_segment_id="osm-way-mg-richmond",
                attributes={"severity": "low", "model_version": "rdd2022-yolov8s-best.pt", "needs_review": True},
            ),
            workflow_status="active",
            confirmations=0,
        ),
    ]

    # Generate inferred traffic congestion events via TrafficIntelligence
    for seg_id, (state, _) in traffic_map.items():
        if state.is_congested:
            seg = seg_by_id[seg_id]
            mid = seg.polyline[min(1, len(seg.polyline) - 1)]
            evt = intel.congestion_event(state, GeoPoint(mid[0], mid[1]), now - timedelta(minutes=2))
            if evt is not None:
                specs.append(SeedEventSpec(event=evt, workflow_status="active", confirmations=3))

    return specs


def build_seed_parking(now: datetime) -> list[ParkingSegmentSeed]:
    return [
        ParkingSegmentSeed(
            road_segment_id="osm-way-cubbon-mg",
            segment_name="MG Road Metro East Bay",
            area="MG Road",
            total_spaces_estimated=18,
            occupied_spaces=11,
            occupancy_rate=0.611,
            confidence=0.88,
            history_window_size=10,
            last_observed=now - timedelta(minutes=1),
            center=GeoPoint(12.9759, 77.6012),
            polyline=((12.9761, 77.5980), (12.9757, 77.6050)),
        ),
        ParkingSegmentSeed(
            road_segment_id="osm-way-mg-richmond",
            segment_name="Brigade Rd - Residency Curbs",
            area="Brigade / Residency",
            total_spaces_estimated=14,
            occupied_spaces=12,
            occupancy_rate=0.857,
            confidence=0.84,
            history_window_size=8,
            last_observed=now - timedelta(minutes=2),
            center=GeoPoint(12.9708, 77.6024),
            polyline=((12.9735, 77.6048), (12.9682, 77.6001)),
        ),
        ParkingSegmentSeed(
            road_segment_id="osm-way-ulsoor-indira",
            segment_name="CMH Road Indiranagar Pockets",
            area="Indiranagar",
            total_spaces_estimated=22,
            occupied_spaces=9,
            occupancy_rate=0.409,
            confidence=0.90,
            history_window_size=10,
            last_observed=now - timedelta(seconds=45),
            center=GeoPoint(12.9806, 77.6308),
            polyline=((12.9815, 77.6255), (12.9794, 77.6365)),
        ),
        ParkingSegmentSeed(
            road_segment_id="osm-way-indira-domlur",
            segment_name="100ft Road Service Lane",
            area="Indiranagar 12th Main",
            total_spaces_estimated=16,
            occupied_spaces=5,
            occupancy_rate=0.312,
            confidence=0.86,
            history_window_size=9,
            last_observed=now - timedelta(minutes=3),
            center=GeoPoint(12.9698, 77.6399),
            polyline=((12.9742, 77.6403), (12.9654, 77.6393)),
        ),
        ParkingSegmentSeed(
            road_segment_id="osm-way-ejipura-kora",
            segment_name="Koramangala 80ft Curbside",
            area="Koramangala 4th Block",
            total_spaces_estimated=20,
            occupied_spaces=14,
            occupancy_rate=0.700,
            confidence=0.82,
            history_window_size=7,
            last_observed=now - timedelta(minutes=2),
            center=GeoPoint(12.9396, 77.6238),
            polyline=((12.9415, 77.6234), (12.9368, 77.6242)),
        ),
        ParkingSegmentSeed(
            road_segment_id="osm-way-cubbon-richmond",
            segment_name="Kasturba Rd Museum Edge",
            area="Cubbon Perimeter",
            total_spaces_estimated=12,
            occupied_spaces=4,
            occupancy_rate=0.333,
            confidence=0.78,
            history_window_size=6,
            last_observed=now - timedelta(minutes=4),
            center=GeoPoint(12.9712, 77.5961),
            polyline=((12.9740, 77.5944), (12.9685, 77.5975)),
        ),
    ]


def build_seed_fleet(now: datetime) -> list[EdgeUnitSeed]:
    return [
        EdgeUnitSeed(
            unit_id="EDGE-KA01-104",
            vehicle_label="BMTC Feeder EV-12",
            corridor="MG Road - Indiranagar",
            status="online",
            latitude=12.9756,
            longitude=77.6066,
            gnss_age_ms=118.0,
            gnss_accuracy_m=4.4,
            imu_harsh_brakes_1h=1,
            model_version="rdd2022-yolov8s-best.pt + yolov8n.pt",
            fps=18.4,
            parking_every_n=5,
            anpr_every_n=15,
            plate_blur_enabled=True,
            buffer_queue_depth=0,
            last_heartbeat=now - timedelta(seconds=6),
        ),
        EdgeUnitSeed(
            unit_id="EDGE-KA01-209",
            vehicle_label="Civic Patrol Van 04",
            corridor="Richmond - Shanthinagar",
            status="online",
            latitude=12.9609,
            longitude=77.5974,
            gnss_age_ms=205.0,
            gnss_accuracy_m=5.9,
            imu_harsh_brakes_1h=4,
            model_version="rdd2022-yolov8s-best.pt + yolov8n.pt",
            fps=15.2,
            parking_every_n=5,
            anpr_every_n=15,
            plate_blur_enabled=True,
            buffer_queue_depth=0,
            last_heartbeat=now - timedelta(seconds=11),
        ),
        EdgeUnitSeed(
            unit_id="EDGE-KA03-087",
            vehicle_label="Ride Fleet Sedan 87",
            corridor="Domlur - Koramangala",
            status="online",
            latitude=12.9482,
            longitude=77.6320,
            gnss_age_ms=162.0,
            gnss_accuracy_m=4.9,
            imu_harsh_brakes_1h=0,
            model_version="rdd2022-yolov8s-best.pt + yolov8n.pt",
            fps=20.0,
            parking_every_n=5,
            anpr_every_n=15,
            plate_blur_enabled=True,
            buffer_queue_depth=0,
            last_heartbeat=now - timedelta(seconds=4),
        ),
        EdgeUnitSeed(
            unit_id="EDGE-KA05-312",
            vehicle_label="Delivery Pod 312",
            corridor="Shanthinagar - Ejipura",
            status="degraded",
            latitude=12.9495,
            longitude=77.6095,
            gnss_age_ms=920.0,  # exceeds 750ms max_alignment_ms
            gnss_accuracy_m=14.6,
            imu_harsh_brakes_1h=6,
            model_version="rdd2022-yolov8s-best.pt + yolov8n.pt",
            fps=9.8,
            parking_every_n=5,
            anpr_every_n=15,
            plate_blur_enabled=True,
            buffer_queue_depth=14,
            last_heartbeat=now - timedelta(seconds=38),
        ),
        EdgeUnitSeed(
            unit_id="EDGE-KA01-415",
            vehicle_label="Smart Dashcam Pilot 15",
            corridor="Ulsoor - CMH Rd",
            status="online",
            latitude=12.9806,
            longitude=77.6308,
            gnss_age_ms=144.0,
            gnss_accuracy_m=4.1,
            imu_harsh_brakes_1h=1,
            model_version="rdd2022-yolov8s-best.pt + yolov8n.pt",
            fps=19.1,
            parking_every_n=5,
            anpr_every_n=15,
            plate_blur_enabled=True,
            buffer_queue_depth=0,
            last_heartbeat=now - timedelta(seconds=8),
        ),
    ]


def load_model_registry() -> list[dict[str, Any]]:
    manifest_path = Path(__file__).resolve().parents[1] / "models" / "manifest.json"
    registry: list[dict[str, Any]] = []
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            for item in data.get("models", []):
                registry.append(
                    {
                        "file": item.get("file", "unknown"),
                        "purpose": item.get("purpose", ""),
                        "status": "downloaded",
                        "license": item.get("license", "Verify license"),
                        "sha256_prefix": str(item.get("sha256", ""))[:12],
                    }
                )
        except Exception:
            pass

    if not any(m["file"] == "rdd2022-yolov8s-best.pt" for m in registry):
        registry.append(
            {
                "file": "rdd2022-yolov8s-best.pt",
                "purpose": "RDD2022 road-damage detector (pothole, longitudinal/transverse/alligator cracks)",
                "status": "downloaded",
                "license": "AGPL-3.0; review before commercial deployment",
                "sha256_prefix": "94945fc2d4fe",
            }
        )

    registry.extend(
        [
            {
                "file": "SAM 3.1",
                "purpose": "Second-stage candidate mask refinement & video tracking",
                "status": "gated_approval_required",
                "license": "Meta SAM license (gated access)",
                "sha256_prefix": "gated",
            },
            {
                "file": "road-defects-india-v1.pt",
                "purpose": "Fine-tuned pothole, crack, speed-breaker, waterlogging & construction detector",
                "status": "training_pending",
                "license": "Internal consented local-dataset artifact",
                "sha256_prefix": "pending",
            },
        ]
    )
    return registry

