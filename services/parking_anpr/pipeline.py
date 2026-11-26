from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

import numpy as np

from .anpr import ANPRPipeline
from .config import ParkingANPRConfig, settings as default_settings
from .detector import ParkingDetector
from .occupancy import OccupancyEstimator
from .privacy import PrivacyManager
from .schemas import (
    DetectedPlate,
    GPSCoord,
    OccupancyReport,
    ParkingObservation,
    VehicleDetection,
)
from .tracker import VehicleTracker

logger = logging.getLogger(__name__)


def _resolve_model_path(relative_path: str) -> str:
    """
    Resolve *relative_path* against the repository root so that the pipeline
    can be instantiated from any working directory.
    """
    # Walk up from this file to the workspace root (Key/)
    here = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.abspath(os.path.join(here, "..", ".."))
    return os.path.join(workspace_root, relative_path)


class ParkingANPRPipeline:
    """
    End-to-end pipeline that combines vehicle detection, tracking, ANPR and
    occupancy estimation for parking-intelligence use cases.

    Processing flow per frame
    -------------------------
    1. Every ``config.frame_skip_parking`` frames: detect all vehicles.
    2. Update the tracker with fresh detections; isolate parked vehicles.
    3. Every ``config.frame_skip_anpr`` frames: run ANPR on parked vehicles.
    4. Estimate roadside occupancy for the current road segment.
    5. Apply privacy masks to plate regions in the frame.
    6. Return a fully populated :class:`ParkingObservation`.
    """

    def __init__(self, config: Optional[ParkingANPRConfig] = None) -> None:
        self.config = config or default_settings

        # Resolve model paths relative to the workspace root.
        vehicle_model = _resolve_model_path(self.config.vehicle_model_path)
        plate_model = _resolve_model_path(
            os.path.join(self.config.models_dir, self.config.plate_model_filename)
        )

        self.detector = ParkingDetector(
            model_path=vehicle_model,
            confidence=self.config.vehicle_confidence,
        )
        self.tracker = VehicleTracker(
            parked_threshold=self.config.parked_frame_threshold,
        )
        self.anpr = ANPRPipeline(
            plate_model_path=plate_model,
            ocr_confidence=self.config.ocr_confidence,
            plate_confidence=self.config.plate_confidence,
        )
        self.occupancy = OccupancyEstimator()
        self.privacy = PrivacyManager()

        self._frame_counter: int = 0
        # Cache of last known vehicle detections between detection frames.
        self._cached_detections: List[VehicleDetection] = []
        # Persistent list of plates seen in the last ANPR window.
        self._last_plates: List[DetectedPlate] = []

        logger.info("ParkingANPRPipeline initialised")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_frame(
        self,
        frame: np.ndarray,
        gps_coord: GPSCoord,
        timestamp: datetime,
        road_segment_id: str = "unknown",
    ) -> ParkingObservation:
        """
        Process a single video frame through the full parking / ANPR pipeline.

        Args:
            frame: BGR image (H, W, 3) as a NumPy array.
            gps_coord: GPS coordinate associated with the frame.
            timestamp: Capture timestamp (UTC preferred).
            road_segment_id: Identifier of the road segment being observed.

        Returns:
            A :class:`ParkingObservation` with all detected data populated.
        """
        self._frame_counter += 1
        fc = self._frame_counter

        # ------------------------------------------------------------------
        # Step 1 — Vehicle detection (every frame_skip_parking frames)
        # ------------------------------------------------------------------
        if fc % self.config.frame_skip_parking == 0:
            raw_detections = self.detector.detect_vehicles(frame, gps_coord)
        else:
            raw_detections = self._cached_detections

        # ------------------------------------------------------------------
        # Step 2 — Tracking + parked-vehicle filtering
        # ------------------------------------------------------------------
        tracked_detections = self.tracker.update(raw_detections, frame.shape)
        parked_vehicles = self.tracker.get_parked_vehicles(tracked_detections)
        self._cached_detections = tracked_detections

        # ------------------------------------------------------------------
        # Step 3 — ANPR (every frame_skip_anpr frames, parked vehicles only)
        # ------------------------------------------------------------------
        detected_plates: List[DetectedPlate] = []
        if fc % self.config.frame_skip_anpr == 0 and parked_vehicles:
            vehicle_boxes = [v.bbox for v in parked_vehicles]
            vehicle_tids = [v.track_id for v in parked_vehicles]
            raw_plates = self.anpr.detect_plates(
                frame,
                vehicle_boxes,
                gps_coord=gps_coord,
                vehicle_track_ids=vehicle_tids,
            )
            # Apply storage anonymisation
            for plate in raw_plates:
                plate.anonymized_text = self.privacy.anonymize_for_storage(plate.raw_text)
            detected_plates = raw_plates
            self._last_plates = detected_plates
        else:
            detected_plates = self._last_plates

        # ------------------------------------------------------------------
        # Step 4 — Occupancy estimation
        # ------------------------------------------------------------------
        occupancy_report: Optional[OccupancyReport] = self.occupancy.estimate_roadside_occupancy(
            frame,
            parked_vehicles,
            road_segment_id,
            timestamp=timestamp,
        )

        # ------------------------------------------------------------------
        # Step 5 — Privacy masking of plate regions in frame
        # ------------------------------------------------------------------
        for plate in detected_plates:
            self.privacy.mask_plate_in_frame(frame, plate.bbox)

        # ------------------------------------------------------------------
        # Step 6 — Build and return observation
        # ------------------------------------------------------------------
        observation = ParkingObservation(
            observation_id=str(uuid4()),
            gps_coord=gps_coord,
            timestamp=timestamp,
            parked_vehicles=parked_vehicles,
            detected_plates=detected_plates,
            occupancy_report=occupancy_report,
            road_segment_id=road_segment_id,
            source="dashcam",
        )

        logger.debug(
            "ParkingANPRPipeline frame #%d: parked=%d plates=%d occupancy=%.1f%%",
            fc,
            len(parked_vehicles),
            len(detected_plates),
            (occupancy_report.occupancy_rate * 100) if occupancy_report else 0.0,
        )
        return observation
