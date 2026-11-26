from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

from .schemas import OccupancyReport, VehicleDetection

logger = logging.getLogger(__name__)

# Minimum number of estimated spaces for any road segment.
_MIN_SPACES = 4

# Confidence assigned when we have a full history window (10 observations).
_MAX_CONFIDENCE = 0.90

# Confidence assigned for a single-observation estimate.
_MIN_CONFIDENCE = 0.50


class OccupancyEstimator:
    """
    Estimates roadside parking occupancy from a sequence of parked-vehicle
    detections on a named road segment.

    The estimator maintains a rolling window of observations per segment so
    that short-term noise (e.g. a vehicle briefly misclassified as parked)
    is smoothed out.
    """

    def __init__(self) -> None:
        # segment_id -> deque of (occupied_spaces, estimated_total) tuples
        self.history: Dict[str, deque] = {}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_history(self, segment_id: str) -> None:
        if segment_id not in self.history:
            self.history[segment_id] = deque(maxlen=10)

    def _smoothed_occupancy(self, segment_id: str) -> float:
        """Return the smoothed occupancy rate from the rolling window."""
        hist = self.history.get(segment_id)
        if not hist:
            return 0.0
        rates = [occ / max(tot, 1) for occ, tot in hist]
        return float(np.mean(rates))

    def _confidence(self, segment_id: str) -> float:
        """Scale confidence linearly with the number of observations on record."""
        n = len(self.history.get(segment_id, []))
        if n == 0:
            return _MIN_CONFIDENCE
        # Linearly interpolate from _MIN_CONFIDENCE (n=1) to _MAX_CONFIDENCE (n=10)
        return _MIN_CONFIDENCE + (_MAX_CONFIDENCE - _MIN_CONFIDENCE) * min(n / 10, 1.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate_roadside_occupancy(
        self,
        frame: np.ndarray,
        parked_vehicles: List[VehicleDetection],
        road_segment_id: str,
        timestamp: datetime | None = None,
    ) -> OccupancyReport:
        """
        Estimate the occupancy of roadside parking spaces on *road_segment_id*.

        The total number of available spaces is estimated conservatively as::

            max(len(parked_vehicles) + 2, _MIN_SPACES)

        This accounts for spaces that might be occupied but whose vehicles
        were not detected, as well as empty spaces around the observed cluster.

        Args:
            frame: Current video frame (not used directly but kept for
                   future spatial analysis extensions).
            parked_vehicles: Vehicles classified as parked in this frame.
            road_segment_id: Identifier of the road segment being analysed.
            timestamp: Observation timestamp; defaults to ``datetime.now(UTC)``.

        Returns:
            :class:`OccupancyReport` with both raw and smoothed estimates.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        self._ensure_history(road_segment_id)

        occupied = len(parked_vehicles)
        total_estimated = max(occupied + 2, _MIN_SPACES)

        self.history[road_segment_id].append((occupied, total_estimated))

        occupancy_rate = round(self._smoothed_occupancy(road_segment_id), 4)
        confidence = round(self._confidence(road_segment_id), 4)

        report = OccupancyReport(
            segment_id=road_segment_id,
            timestamp=timestamp,
            total_spaces_estimated=total_estimated,
            occupied_spaces=occupied,
            occupancy_rate=occupancy_rate,
            confidence=confidence,
        )

        logger.debug(
            "OccupancyEstimator [%s]: %d/%d spaces occupied (rate=%.2f, conf=%.2f)",
            road_segment_id,
            occupied,
            total_estimated,
            occupancy_rate,
            confidence,
        )
        return report
