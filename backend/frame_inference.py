"""Ephemeral dual-model dashcam inference (RDD2022 road defects + YOLOv8n vehicles).

The uploaded image bytes are decoded in memory and never written to disk.
Only normalized RoadEvent metadata and bounding boxes are returned to callers.
"""
from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from threading import Lock
import time
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]

MODEL_PATH = Path(
    os.getenv(
        "ROAD_DEFECT_MODEL_PATH",
        str(_REPO_ROOT / "models" / "rdd2022-yolov8s-best.pt"),
    )
)
VEHICLE_MODEL_PATH = Path(
    os.getenv(
        "VEHICLE_MODEL_PATH",
        str(_REPO_ROOT / "services" / "parking_anpr" / "models" / "yolov8n.pt"),
    )
)

MODEL_VERSION = "rdd2022-yolov8s-best.pt"
_defect_model: Any | None = None
_vehicle_model: Any | None = None
_vehicle_model_unavailable = False
_model_lock = Lock()

# The RDD2022 model detects four defect labels. The shared RoadEvent contract
# represents crack variants as `crack` while keeping source_label in attributes.
MODEL_TO_EVENT_LABEL = {
    "pothole": "pothole",
    "longitudinal_crack": "crack",
    "transverse_crack": "crack",
    "alligator_crack": "crack",
}

VEHICLE_CLASS_NAMES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


def _get_defect_model() -> Any:
    global _defect_model
    with _model_lock:
        if _defect_model is not None:
            return _defect_model
        if not MODEL_PATH.is_file():
            raise RuntimeError(f"Road-defect model is unavailable at {MODEL_PATH}")
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Road-defect inference requires the ultralytics runtime") from exc
        _defect_model = YOLO(str(MODEL_PATH))
        return _defect_model


def _get_vehicle_model() -> Any | None:
    global _vehicle_model, _vehicle_model_unavailable
    with _model_lock:
        if _vehicle_model is not None:
            return _vehicle_model
        if _vehicle_model_unavailable or not VEHICLE_MODEL_PATH.is_file():
            _vehicle_model_unavailable = True
            return None
        try:
            from ultralytics import YOLO
            _vehicle_model = YOLO(str(VEHICLE_MODEL_PATH))
            return _vehicle_model
        except Exception:
            _vehicle_model_unavailable = True
            return None


def _decode_rgb_image(image_bytes: bytes) -> Any:
    if not image_bytes:
        raise ValueError("uploaded frame is empty")
    try:
        from PIL import Image
        return Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError("uploaded frame is not a valid image") from exc


def infer_dashcam_frame(
    image_bytes: bytes,
    defect_conf: float = 0.35,
    vehicle_conf: float = 0.40,
) -> dict[str, Any]:
    """Run road-defect and vehicle detection in memory without retaining frame bytes."""
    image = _decode_rgb_image(image_bytes)
    width, height = image.size
    t0 = time.perf_counter()

    defect_model = _get_defect_model()
    defect_results = defect_model.predict(
        source=image,
        conf=defect_conf,
        imgsz=512,
        verbose=False,
    )

    candidates: list[dict[str, Any]] = []
    if defect_results:
        res = defect_results[0]
        if res.boxes is not None:
            for box in res.boxes:
                model_label = str(res.names[int(box.cls.item())])
                event_label = MODEL_TO_EVENT_LABEL.get(model_label)
                if event_label is None:
                    continue
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                nx1 = max(0.0, min(1.0, x1 / max(1, width)))
                ny1 = max(0.0, min(1.0, y1 / max(1, height)))
                nx2 = max(0.0, min(1.0, x2 / max(1, width)))
                ny2 = max(0.0, min(1.0, y2 / max(1, height)))
                area_ratio = max(0.0, min(1.0, (nx2 - nx1) * (ny2 - ny1)))
                candidates.append(
                    {
                        "label": event_label,
                        "source_label": model_label,
                        "confidence": round(float(box.conf.item()), 4),
                        "bbox_area_ratio": round(area_ratio, 6),
                        "bbox_xyxy": [round(v, 1) for v in (x1, y1, x2, y2)],
                        "bbox_norm": [round(v, 4) for v in (nx1, ny1, nx2, ny2)],
                    }
                )
    candidates.sort(key=lambda c: c["confidence"], reverse=True)

    vehicles: list[dict[str, Any]] = []
    vehicle_model = _get_vehicle_model()
    active_model_version = MODEL_VERSION
    if vehicle_model is not None:
        active_model_version = f"{MODEL_VERSION} + yolov8n.pt"
        veh_results = vehicle_model.predict(
            source=image,
            conf=vehicle_conf,
            classes=list(VEHICLE_CLASS_NAMES.keys()),
            imgsz=512,
            verbose=False,
        )
        if veh_results and veh_results[0].boxes is not None:
            for box in veh_results[0].boxes:
                cls_id = int(box.cls.item())
                cls_name = VEHICLE_CLASS_NAMES.get(cls_id)
                if not cls_name:
                    continue
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                nx1 = max(0.0, min(1.0, x1 / max(1, width)))
                ny1 = max(0.0, min(1.0, y1 / max(1, height)))
                nx2 = max(0.0, min(1.0, x2 / max(1, width)))
                ny2 = max(0.0, min(1.0, y2 / max(1, height)))
                nw = max(0.01, nx2 - nx1)
                nh = max(0.01, ny2 - ny1)
                # Lower-center rear/front plate band for on-canvas privacy masking
                plate_box = [
                    round(nx1 + nw * 0.25, 4),
                    round(ny1 + nh * 0.66, 4),
                    round(nx1 + nw * 0.75, 4),
                    round(ny1 + nh * 0.88, 4),
                ]
                vehicles.append(
                    {
                        "class_name": cls_name,
                        "confidence": round(float(box.conf.item()), 4),
                        "bbox_xyxy": [round(v, 1) for v in (x1, y1, x2, y2)],
                        "bbox_norm": [round(v, 4) for v in (nx1, ny1, nx2, ny2)],
                        "plate_blur_box_norm": plate_box,
                    }
                )

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    return {
        "model_version": active_model_version,
        "image_size": [width, height],
        "inference_ms": elapsed_ms,
        "candidates": candidates,
        "vehicles": vehicles,
    }


def infer_road_defects(image_bytes: bytes, confidence_threshold: float = 0.45) -> list[dict[str, Any]]:
    """Return normalized defect candidates from an image held entirely in memory."""
    result = infer_dashcam_frame(image_bytes, defect_conf=confidence_threshold)
    return result["candidates"]
