from __future__ import annotations

import logging
from collections import deque
from typing import Dict, List, Tuple

import numpy as np

from .schemas import VehicleDetection

logger = logging.getLogger(__name__)


class VehicleTracker:
    """
    Wraps ``supervision.ByteTrack`` to assign persistent track IDs to vehicle
    detections and determine which vehicles are parked (stationary).
    """

    def __init__(self, parked_threshold: int = 30) -> None:
        self.parked_threshold = parked_threshold
        self._init_tracker()
        # track_id -> deque of (cx, cy) center positions
        self.track_history: Dict[int, deque] = {}

    def _init_tracker(self) -> None:
        try:
            import supervision as sv  # type: ignore

            self.tracker = sv.ByteTrack()
        except Exception as exc:
            logger.error("VehicleTracker: could not initialise ByteTrack — %s", exc)
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bbox_center(bbox: List[float]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0

    def _to_sv_detections(
        self, detections: List[VehicleDetection], frame_shape: Tuple[int, ...]
    ):
        """Convert our schema detections to a ``supervision.Detections`` object."""
        import supervision as sv  # type: ignore

        if not detections:
            return sv.Detections.empty()

        xyxy = np.array([d.bbox for d in detections], dtype=np.float32)
        confidence = np.array([d.confidence for d in detections], dtype=np.float32)
        class_id = np.array([d.class_id for d in detections], dtype=int)

        return sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        detections: List[VehicleDetection],
        frame_shape: Tuple[int, ...],
    ) -> List[VehicleDetection]:
        """
        Update the tracker with the current frame's detections.

        Args:
            detections: Raw detections from :class:`ParkingDetector`.
            frame_shape: ``(H, W[, C])`` shape of the source frame.

        Returns:
            The same detections enriched with ``track_id``.
        """
        sv_dets = self._to_sv_detections(detections, frame_shape)
        tracked = self.tracker.update_with_detections(sv_dets)

        updated: List[VehicleDetection] = []
        for i, track_id in enumerate(tracked.tracker_id):
            if track_id is None:
                continue

            tid = int(track_id)

            # Reconstruct VehicleDetection from tracked box
            bbox = tracked.xyxy[i].tolist()
            conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0
            cls_id = int(tracked.class_id[i]) if tracked.class_id is not None else 0

            from .detector import VEHICLE_CLASS_NAMES  # local import to avoid circularity

            det = VehicleDetection(
                bbox=bbox,
                confidence=conf,
                class_id=cls_id,
                class_name=VEHICLE_CLASS_NAMES.get(cls_id, "vehicle"),
                track_id=tid,
            )
            updated.append(det)

            # Update position history
            cx, cy = self._bbox_center(bbox)
            if tid not in self.track_history:
                self.track_history[tid] = deque(maxlen=60)
            self.track_history[tid].append((cx, cy))

        return updated

    def is_parked(self, track_id: int) -> bool:
        """
        Return True if the vehicle with *track_id* has been stationary for at
        least ``parked_threshold`` frames (std of positions < 10 px).
        """
        history = self.track_history.get(track_id)
        if history is None or len(history) < self.parked_threshold:
            return False

        positions = np.array(list(history))
        std_x = float(np.std(positions[:, 0]))
        std_y = float(np.std(positions[:, 1]))
        return (std_x < 10.0) and (std_y < 10.0)

    def get_parked_vehicles(
        self, detections: List[VehicleDetection]
    ) -> List[VehicleDetection]:
        """Filter *detections* to only those whose track is currently parked."""
        return [d for d in detections if d.track_id is not None and self.is_parked(d.track_id)]
