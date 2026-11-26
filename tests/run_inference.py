"""
run_inference.py
================
Full pipeline demo: RDD2022 road damage + YOLOv8n vehicle detection + ANPR plate detection.
Runs on the synthetic road scene and prints structured results.
"""
import cv2
import numpy as np
import json
import time
import torch
from datetime import datetime, timezone
from ultralytics import YOLO

# ── Load image ─────────────────────────────────────────────────────────────────
IMG_PATH = "tests/sample_images/road_scene.jpg"
img = cv2.imread(IMG_PATH)
H, W = img.shape[:2]
GPS = {"lat": 12.9716, "lon": 77.5946, "accuracy_m": 4.2, "speed_kph": 38.0}
TS  = datetime.now(timezone.utc).isoformat()
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

results = {
    "timestamp": TS,
    "gps": GPS,
    "frame_size": f"{W}x{H}",
    "device": DEVICE,
    "detections": {}
}

print(f"\nDevice: {DEVICE} | Frame: {W}x{H} | GPS: {GPS['lat']}N, {GPS['lon']}E\n")

# ── 1. RDD2022 Road Damage Detector ───────────────────────────────────────────
print("=" * 60)
print("[1/3] RDD2022 Road Damage Detector")
print("=" * 60)
rdd = YOLO("models/rdd2022-yolov8s-best.pt")
t0 = time.perf_counter()
r = rdd(img, conf=0.25, verbose=False, device=DEVICE)[0]
rdd_ms = (time.perf_counter() - t0) * 1000
road_events = []
for b in r.boxes:
    cls  = int(b.cls[0])
    conf = float(b.conf[0])
    x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
    area = (x2 - x1) * (y2 - y1)
    entry = {
        "class": rdd.names[cls],
        "confidence": round(conf, 3),
        "bbox": [x1, y1, x2, y2],
        "area_px": area,
        "gps": GPS,
    }
    road_events.append(entry)
    print(f"  DETECTED  {rdd.names[cls]:25s}  conf={conf:.3f}  bbox=[{x1},{y1},{x2},{y2}]  area={area}px")

if not road_events:
    print("  (no road damage detected above conf=0.25)")
print(f"\n  Inference time : {rdd_ms:.1f} ms")
print(f"  Detections     : {len(road_events)}")
results["detections"]["road_damage"] = road_events

# ── 2. YOLOv8n Vehicle Detector ───────────────────────────────────────────────
print()
print("=" * 60)
print("[2/3] YOLOv8n Vehicle Detector")
print("=" * 60)
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
veh_model = YOLO("services/parking_anpr/models/yolov8n.pt")
t0 = time.perf_counter()
r2 = veh_model(img, conf=0.30, verbose=False, device=DEVICE)[0]
veh_ms = (time.perf_counter() - t0) * 1000
vehicles = []
for b in r2.boxes:
    cls = int(b.cls[0])
    if cls not in VEHICLE_CLASSES:
        continue
    conf = float(b.conf[0])
    x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
    entry = {
        "class": VEHICLE_CLASSES[cls],
        "confidence": round(conf, 3),
        "bbox": [x1, y1, x2, y2],
    }
    vehicles.append(entry)
    print(f"  DETECTED  {VEHICLE_CLASSES[cls]:15s}  conf={conf:.3f}  bbox=[{x1},{y1},{x2},{y2}]")

if not vehicles:
    print("  (no vehicles detected)")
print(f"\n  Inference time : {veh_ms:.1f} ms")
print(f"  Detections     : {len(vehicles)}")
results["detections"]["vehicles"] = vehicles

# ── 3. ANPR Plate Detector ────────────────────────────────────────────────────
print()
print("=" * 60)
print("[3/3] ANPR License Plate Detector")
print("=" * 60)
plate_model = YOLO("services/parking_anpr/models/best.pt")
plates_found = []
plate_total_ms = 0.0

for v in vehicles:
    x1, y1, x2, y2 = v["bbox"]
    pw, ph = x2 - x1, y2 - y1
    ex1 = max(0, x1 - int(pw * 0.2))
    ey1 = max(0, y1 - int(ph * 0.2))
    ex2 = min(W, x2 + int(pw * 0.2))
    ey2 = min(H, y2 + int(ph * 0.2))
    crop = img[ey1:ey2, ex1:ex2]
    if crop.size == 0:
        continue

    t0 = time.perf_counter()
    pr = plate_model(crop, conf=0.25, verbose=False, device=DEVICE)[0]
    pl_ms = (time.perf_counter() - t0) * 1000
    plate_total_ms += pl_ms

    for pb in pr.boxes:
        pconf = float(pb.conf[0])
        px1, py1, px2, py2 = [int(c) for c in pb.xyxy[0].tolist()]
        plate_crop = crop[py1:py2, px1:px2]
        abs_bbox = [ex1 + px1, ey1 + py1, ex1 + px2, ey1 + py2]
        entry = {
            "vehicle_class": v["class"],
            "plate_bbox": abs_bbox,
            "detection_confidence": round(pconf, 3),
            "crop_size": f"{plate_crop.shape[1]}x{plate_crop.shape[0]}",
        }
        plates_found.append(entry)
        print(f"  PLATE  vehicle={v['class']:12s}  conf={pconf:.3f}  bbox={abs_bbox}  crop={entry['crop_size']}")

if not plates_found:
    print("  (no plates detected)")
print(f"\n  Inference time : {plate_total_ms:.1f} ms total across {len(vehicles)} vehicle crops")
print(f"  Detections     : {len(plates_found)}")
results["detections"]["license_plates"] = plates_found

# ── 4. SAM 3.1 architecture info ──────────────────────────────────────────────
print()
print("=" * 60)
print("[4/4] SAM 3.1 Multiplex — Model Architecture Info")
print("=" * 60)
sam_ckpt = torch.load("models/sam3.1/sam3.1_multiplex.pt", map_location="cpu", weights_only=False)
sam_keys = list(sam_ckpt.keys())
sections = {}
for k in sam_keys:
    top = k.split(".")[0]
    sections[top] = sections.get(top, 0) + 1
param_count = sum(sam_ckpt[k].numel() for k in sam_keys if hasattr(sam_ckpt[k], "numel"))
print(f"  Checkpoint keys  : {len(sam_keys)}")
print(f"  Total parameters : {param_count / 1e6:.1f}M")
print(f"  Architecture     : detector ({sections.get('detector', 0)} tensors) + tracker ({sections.get('tracker', 0)} tensors)")
print(f"  File size        : 3,340 MB")
print(f"  Status           : Loaded (CPU). Requires SAM2/SAMURAI Python package for inference.")
results["sam31"] = {
    "total_tensors": len(sam_keys),
    "params_M": round(param_count / 1e6, 1),
    "sections": sections,
    "status": "weights_loaded_requires_sam2_package",
}

# ── 5. Annotated output image ─────────────────────────────────────────────────
out = img.copy()

# Draw road damage boxes (red)
for ev in road_events:
    x1, y1, x2, y2 = ev["bbox"]
    cv2.rectangle(out, (x1, y1), (x2, y2), (0, 0, 255), 2)
    label = f"{ev['class']} {ev['confidence']:.2f}"
    cv2.rectangle(out, (x1, y1 - 20), (x1 + len(label)*9, y1), (0, 0, 255), -1)
    cv2.putText(out, label, (x1 + 2, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

# Draw vehicle boxes (green)
for veh in vehicles:
    x1, y1, x2, y2 = veh["bbox"]
    cv2.rectangle(out, (x1, y1), (x2, y2), (0, 220, 60), 2)
    label = f"{veh['class']} {veh['confidence']:.2f}"
    cv2.rectangle(out, (x1, y1 - 20), (x1 + len(label)*9, y1), (0, 180, 50), -1)
    cv2.putText(out, label, (x1 + 2, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

# Draw plate boxes (yellow)
for pl in plates_found:
    x1, y1, x2, y2 = pl["plate_bbox"]
    cv2.rectangle(out, (x1, y1), (x2, y2), (0, 220, 255), 2)
    cv2.putText(out, f"PLATE {pl['detection_confidence']:.2f}", (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1)

# Stats overlay
total_ms = rdd_ms + veh_ms + plate_total_ms
cv2.rectangle(out, (0, 0), (560, 90), (0, 0, 0), -1)
cv2.putText(out, f"RDD2022: {len(road_events)} event(s)  {rdd_ms:.0f}ms", (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 180, 255), 1)
cv2.putText(out, f"Vehicles: {len(vehicles)} detected  {veh_ms:.0f}ms", (10, 50),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 220, 60), 1)
cv2.putText(out, f"Plates: {len(plates_found)} detected  |  Total: {total_ms:.0f}ms  ({1000/total_ms:.0f} FPS)", (10, 76),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 1)

cv2.imwrite("tests/sample_images/road_scene_annotated.jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 95])
print()

# ── Final summary ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("PIPELINE RESULTS")
print("=" * 60)
print(f"  Device          : {DEVICE}")
print(f"  GPS             : {GPS['lat']}N, {GPS['lon']}E  @  {GPS['speed_kph']} km/h")
print(f"  Road damage     : {len(road_events)} event(s)  ({rdd_ms:.1f} ms)")
print(f"  Vehicles        : {len(vehicles)} detected   ({veh_ms:.1f} ms)")
print(f"  License plates  : {len(plates_found)} detected   ({plate_total_ms:.1f} ms)")
print(f"  Total inference : {total_ms:.1f} ms  ({1000/total_ms:.1f} FPS)")
print(f"  SAM 3.1         : {param_count/1e6:.1f}M params loaded (needs sam2 package for inference)")
print()
print(json.dumps(results, indent=2))

# Save JSON results
with open("tests/sample_images/inference_results.json", "w") as f:
    json.dump(results, f, indent=2)
print("\nAnnotated image saved: tests/sample_images/road_scene_annotated.jpg")
print("JSON results saved:    tests/sample_images/inference_results.json")
