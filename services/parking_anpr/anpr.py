from __future__ import annotations

import logging
import os
from typing import List, Optional
from uuid import uuid4

import numpy as np

from .schemas import DetectedPlate, GPSCoord

logger = logging.getLogger(__name__)

# Fraction by which to expand the vehicle crop before running the plate model.
_EXPAND_RATIO = 0.20


def _expand_bbox(
    bbox: List[float],
    expand: float,
    img_h: int,
    img_w: int,
) -> List[int]:
    """Return an expanded bounding box clipped to the image boundaries."""
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    x1 = max(0, int(x1 - w * expand))
    y1 = max(0, int(y1 - h * expand))
    x2 = min(img_w, int(x2 + w * expand))
    y2 = min(img_h, int(y2 + h * expand))
    return [x1, y1, x2, y2]


class ANPRPipeline:
    """
    Automatic Number-Plate Recognition pipeline.

    1. Crops vehicle regions from the frame (with 20 % padding).
    2. Runs a YOLOv8 license-plate detector on each crop.
    3. Runs EasyOCR on each detected plate crop.
    4. Returns :class:`DetectedPlate` instances that exceed confidence
       thresholds.
    """

    def __init__(
        self,
        plate_model_path: str,
        ocr_confidence: float = 0.60,
        plate_confidence: float = 0.50,
    ) -> None:
        self.ocr_confidence = ocr_confidence
        self.plate_confidence = plate_confidence
        self._load_plate_model(plate_model_path)
        self._load_ocr()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _load_plate_model(self, model_path: str) -> None:
        try:
            from ultralytics import YOLO  # type: ignore

            self.plate_model = YOLO(model_path)
            logger.info("ANPRPipeline: plate model loaded from %s", model_path)
        except Exception as exc:
            logger.error("ANPRPipeline: failed to load plate model — %s", exc)
            raise

    def _load_ocr(self) -> None:
        try:
            import easyocr  # type: ignore

            self.ocr_reader = easyocr.Reader(["en"], gpu=False)
            logger.info("ANPRPipeline: EasyOCR reader initialised")
        except Exception as exc:
            logger.error("ANPRPipeline: failed to initialise EasyOCR — %s", exc)
            raise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def anonymize_plate(self, text: str) -> str:
        """
        Anonymise a plate string by masking all characters after the first 4
        with 'X'.

        Examples
        --------
        >>> ANPRPipeline.anonymize_plate(None, "MH12AB1234")
        'MH12XXXXXX'
        >>> ANPRPipeline.anonymize_plate(None, "AB12")
        'AB12'
        """
        if len(text) <= 4:
            return text
        return text[:4] + "X" * (len(text) - 4)

    def detect_plates(
        self,
        frame: np.ndarray,
        vehicle_boxes: List[List[float]],
        gps_coord: Optional[GPSCoord] = None,
        vehicle_track_ids: Optional[List[Optional[int]]] = None,
    ) -> List[DetectedPlate]:
        """
        Detect and read license plates for the given vehicle bounding boxes.

        Args:
            frame: Full BGR frame (H, W, 3).
            vehicle_boxes: List of ``[x1, y1, x2, y2]`` bounding boxes in
                           absolute pixel coordinates.
            gps_coord: GPS location associated with this frame.
            vehicle_track_ids: Parallel list of track IDs (may be None per
                               vehicle).

        Returns:
            List of :class:`DetectedPlate` instances.
        """
        from datetime import datetime, timezone

        img_h, img_w = frame.shape[:2]
        plates: List[DetectedPlate] = []

        if vehicle_track_ids is None:
            vehicle_track_ids = [None] * len(vehicle_boxes)

        if gps_coord is None:
            gps_coord = GPSCoord(lat=0.0, lon=0.0, timestamp=datetime.now(timezone.utc))

        for veh_bbox, track_id in zip(vehicle_boxes, vehicle_track_ids):
            # --- Expand and crop the vehicle region ---
            ex1, ey1, ex2, ey2 = _expand_bbox(veh_bbox, _EXPAND_RATIO, img_h, img_w)
            vehicle_crop = frame[ey1:ey2, ex1:ex2]

            if vehicle_crop.size == 0:
                continue

            # --- Run plate detector on vehicle crop ---
            try:
                plate_results = self.plate_model(vehicle_crop, verbose=False)
            except Exception as exc:
                logger.warning("ANPRPipeline: plate detection failed — %s", exc)
                continue

            if not plate_results:
                continue

            plate_boxes = plate_results[0].boxes
            if plate_boxes is None or len(plate_boxes) == 0:
                continue

            for pbox in plate_boxes:
                p_conf = float(pbox.conf[0].item())
                if p_conf < self.plate_confidence:
                    continue

                px1, py1, px2, py2 = [int(v) for v in pbox.xyxy[0].tolist()]
                plate_crop = vehicle_crop[py1:py2, px1:px2]
                if plate_crop.size == 0:
                    continue

                # --- OCR ---
                try:
                    ocr_results = self.ocr_reader.readtext(plate_crop, detail=1)
                except Exception as exc:
                    logger.warning("ANPRPipeline: OCR failed — %s", exc)
                    continue

                if not ocr_results:
                    continue

                # Merge all OCR text chunks for this plate crop
                best_conf = 0.0
                raw_parts: List[str] = []
                for (_bbox, text, ocr_conf) in ocr_results:
                    if ocr_conf >= self.ocr_confidence:
                        raw_parts.append(text.strip().upper())
                        best_conf = max(best_conf, ocr_conf)

                if not raw_parts:
                    continue

                raw_text = " ".join(raw_parts)
                anonymized = self.anonymize_plate(raw_text.replace(" ", ""))

                # Convert plate bbox back to frame absolute coordinates
                abs_bbox = [
                    ex1 + px1,
                    ey1 + py1,
                    ex1 + px2,
                    ey1 + py2,
                ]

                plates.append(
                    DetectedPlate(
                        plate_id=str(uuid4()),
                        bbox=[float(v) for v in abs_bbox],
                        raw_text=raw_text,
                        anonymized_text=anonymized,
                        ocr_confidence=best_conf,
                        detection_confidence=p_conf,
                        vehicle_track_id=track_id,
                        gps_coord=gps_coord,
                        timestamp=datetime.now(timezone.utc),
                    )
                )

        return plates
