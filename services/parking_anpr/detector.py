from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

from .schemas import GPSCoord, VehicleDetection

logger = logging.getLogger(__name__)

# COCO class IDs for vehicles: car=2, motorcycle=3, bus=5, truck=7
VEHICLE_CLASS_IDS = {2, 3, 5, 7}
VEHICLE_CLASS_NAMES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


class ParkingDetector:
    """
    Detects vehicles in a frame using a YOLOv8 model.
    Filters to road-vehicle classes (car, motorcycle, bus, truck).
    """

    def __init__(self, model_path: str, confidence: float = 0.45) -> None:
        self.confidence_threshold = confidence
        self._load_model(model_path)

    def _load_model(self, model_path: str) -> None:
        """Load YOLOv8 model from disk. Deferred import to allow mocking in tests."""
        try:
            from ultralytics import YOLO  # type: ignore

            self.model = YOLO(model_path)
            logger.info("ParkingDetector: loaded model from %s", model_path)
        except Exception as exc:
            logger.error("ParkingDetector: failed to load model — %s", exc)
            raise

    def detect_vehicles(
        self,
        frame: np.ndarray,
        gps_coord: Optional[GPSCoord] = None,
    ) -> List[VehicleDetection]:
        """
        Run YOLOv8 inference on *frame* and return vehicle detections.

        Args:
            frame: BGR image as a NumPy array (H, W, 3).
            gps_coord: Optional GPS coordinate — stored for downstream use but
                       not used in detection logic.

        Returns:
            List of :class:`VehicleDetection` instances, one per vehicle found.
        """
        results = self.model(frame, verbose=False)
        detections: List[VehicleDetection] = []

        if not results:
            return detections

        result = results[0]
        boxes = result.boxes

        if boxes is None or len(boxes) == 0:
            return detections

        for box in boxes:
            cls_id = int(box.cls[0].item())
            if cls_id not in VEHICLE_CLASS_IDS:
                continue

            conf = float(box.conf[0].item())
            if conf < self.confidence_threshold:
                continue

            xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
            detections.append(
                VehicleDetection(
                    bbox=xyxy,
                    confidence=conf,
                    class_id=cls_id,
                    class_name=VEHICLE_CLASS_NAMES.get(cls_id, "vehicle"),
                )
            )

        logger.debug("ParkingDetector: detected %d vehicle(s)", len(detections))
        return detections
