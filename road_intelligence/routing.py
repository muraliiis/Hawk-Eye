from __future__ import annotations

import heapq
from dataclasses import dataclass
from math import inf


@dataclass(frozen=True)
class RoadEdge:
    start: str
    end: str
    distance_km: float
    travel_minutes: float
    road_quality_penalty: float = 0.0
    hazard_penalty: float = 0.0
    congestion_penalty: float = 0.0
    legal_speed_limit_kph: int | None = None


@dataclass(frozen=True)
class RouteResult:
    nodes: tuple[str, ...]
    score: float
    distance_km: float
    travel_minutes: float
    profile: str


@dataclass(frozen=True)
class SpeedAdvisory:
    advisory_speed_kph: int
    legal_speed_limit_kph: int | None
    reason: str


class Router:
    PROFILES = {
        "fastest": (0.9, 0.03, 0.04, 0.03),
        "safest": (0.25, 0.15, 0.35, 0.25),
        "smoothest": (0.25, 0.10, 0.45, 0.20),
        "balanced": (0.5, 0.10, 0.22, 0.18),
    }

    def __init__(self, edges: list[RoadEdge]) -> None:
        self.graph: dict[str, list[RoadEdge]] = {}
        for edge in edges:
            if edge.distance_km < 0 or edge.travel_minutes < 0:
                raise ValueError("edge distance and time must be non-negative")
            self.graph.setdefault(edge.start, []).append(edge)

    def route(self, origin: str, destination: str, profile: str = "balanced") -> RouteResult:
        if profile not in self.PROFILES:
            raise ValueError(f"unknown profile: {profile}")
        weights = self.PROFILES[profile]
        queue = [(0.0, origin, (origin,), 0.0, 0.0)]
        best = {origin: 0.0}
        while queue:
            score, node, path, distance, minutes = heapq.heappop(queue)
            if node == destination:
                return RouteResult(path, round(score, 3), round(distance, 3), round(minutes, 3), profile)
            if score != best.get(node):
                continue
            for edge in self.graph.get(node, []):
                edge_score = (weights[0] * edge.travel_minutes + weights[1] * edge.distance_km +
                              weights[2] * edge.road_quality_penalty + weights[3] * (edge.hazard_penalty + edge.congestion_penalty))
                candidate = score + edge_score
                if candidate < best.get(edge.end, inf):
                    best[edge.end] = candidate
                    heapq.heappush(queue, (candidate, edge.end, path + (edge.end,), distance + edge.distance_km, minutes + edge.travel_minutes))
        raise ValueError("no route exists between origin and destination")

    @staticmethod
    def speed_advisory(legal_speed_limit_kph: int | None, hazard: str | None, distance_to_hazard_m: float | None) -> SpeedAdvisory:
        base = legal_speed_limit_kph or 40
        if hazard and distance_to_hazard_m is not None and distance_to_hazard_m <= 80:
            reduction = 20 if hazard in {"pothole", "speed_breaker", "sharp_curve"} else 10
            return SpeedAdvisory(max(10, base - reduction), legal_speed_limit_kph, f"Approaching {hazard}")
        return SpeedAdvisory(base, legal_speed_limit_kph, "No nearby hazard adjustment")
