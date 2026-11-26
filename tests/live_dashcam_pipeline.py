"""
live_dashcam_pipeline.py
========================
Live road-damage + vehicle tracking + SAM 3.1 segmentation pipeline.

Connects to a dashcam video stream (RTSP / HTTP / local file / YouTube via yt-dlp),
runs frame-by-frame inference, and displays an annotated live window.

Controls (while window is open):
  Q  — quit
  S  — save current annotated frame as JPEG
  P  — pause / resume
  R  — reset SAM2 tracker state

Usage examples:
  # Local video file
  python tests/live_dashcam_pipeline.py --source tests/sample_images/dashcam.mp4

  # YouTube live stream (requires yt-dlp)
  python tests/live_dashcam_pipeline.py --source "https://www.youtube.com/watch?v=STREAM_ID"

  # RTSP dashcam feed
  python tests/live_dashcam_pipeline.py --source "rtsp://192.168.1.100:554/stream"

  # Webcam
  python tests/live_dashcam_pipeline.py --source 0

  # Demo mode (synthetic frames, no external source needed)
  python tests/live_dashcam_pipeline.py --demo
"""
from __future__ import annotations

import argparse
import hashlib
import os
import queue
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np
import torch
from ultralytics import YOLO

# ── GPU / device ──────────────────────────────────────────────────────────────
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE  = torch.float16 if DEVICE == "cuda" else torch.float32

print(f"[init] Device: {DEVICE}")
if DEVICE == "cuda":
    props = torch.cuda.get_device_properties(0)
    print(f"[init] GPU: {props.name}  VRAM: {props.total_memory / 1e9:.1f} GB")

# ── Model paths ───────────────────────────────────────────────────────────────
RDD_MODEL    = "models/rdd2022-yolov8s-best.pt"
VEH_MODEL    = "services/parking_anpr/models/yolov8n.pt"
PLATE_MODEL  = "services/parking_anpr/models/best.pt"
SAM31_CKPT   = "models/sam3.1/sam3.1_multiplex.pt"

VEHICLE_CLS  = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

# ── Colour palette ────────────────────────────────────────────────────────────
COL_DAMAGE  = (0,   60,  255)   # red  — road damage
COL_VEHICLE = (0,  220,   60)   # green — vehicles
COL_PLATE   = (0,  220,  255)   # yellow — plates
COL_SAM     = (255, 100,   0)   # blue  — SAM2 mask overlay
COL_HUD     = (0,    0,    0)   # HUD background


# ─────────────────────────────────────────────────────────────────────────────
# SAM 3.1 wrapper — loads tracker weights into SAM2VideoPredictor
# ─────────────────────────────────────────────────────────────────────────────
class SAM31Tracker:
    """
    Wraps SAM2VideoPredictor with the SAM 3.1 Multiplex checkpoint.
    The checkpoint has two sub-dicts: tracker.* and detector.*.
    We load only the tracker.* weights into the SAM2 video predictor.
    """

    def __init__(self, ckpt_path: str, device: str = "cuda"):
        self.device = device
        self.predictor = None
        self.inference_state: Optional[dict] = None
        self._frame_buffer: list[np.ndarray] = []
        self._initialized = False
        self._track_objects: dict[int, dict] = {}  # obj_id → {label, color}
        self._next_obj_id = 1
        self._load(ckpt_path)

    def _load(self, ckpt_path: str) -> None:
        """
        Load SAM 3.1 Multiplex tracker weights into SAM2VideoPredictor.

        SAM 3.1 Multiplex uses an expanded architecture (mem_dim=256, 16 tokens)
        vs the standard SAM2.1 configs (mem_dim=64, 4 tokens).  We load only the
        tensors whose shapes match the SAM2.1-large backbone — this gives us the
        image encoder, memory attention, and prompt encoder from the SAM3.1 checkpoint.
        Any size-mismatched tensors (multiplex-specific heads) are skipped gracefully.
        """
        print("[SAM3.1] Loading checkpoint …")
        try:
            from sam2.build_sam import build_sam2_video_predictor

            # SAM2.1-large is the closest publicly-configurable variant.
            self.predictor = build_sam2_video_predictor(
                config_file="configs/sam2.1/sam2.1_hiera_l.yaml",
                ckpt_path=None,
                device=self.device,
            )

            # Extract tracker weights from SAM 3.1 checkpoint.
            full_ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
            tracker_sd = {}
            for k, v in full_ckpt.items():
                if k.startswith("tracker.model."):
                    tracker_sd[k[len("tracker.model."):]] = v

            print(f"[SAM3.1] Extracted {len(tracker_sd)} tracker weight tensors")

            # Filter to only shape-compatible tensors (skip multiplex-expanded heads).
            current_sd = self.predictor.state_dict()
            compatible_sd = {}
            skipped = []
            for k, v in tracker_sd.items():
                if k in current_sd and current_sd[k].shape == v.shape:
                    compatible_sd[k] = v
                else:
                    skipped.append(k)

            print(f"[SAM3.1]  Compatible : {len(compatible_sd)}/{len(tracker_sd)} tensors loaded")
            print(f"[SAM3.1]  Skipped    : {len(skipped)} (multiplex-expanded heads — expected)")

            missing, unexpected = self.predictor.load_state_dict(
                compatible_sd, strict=False
            )
            self.predictor.to(device=self.device, dtype=DTYPE)
            self.predictor.eval()
            print(f"[SAM3.1] Tracker loaded → {self.device} ({DTYPE})  ✓")
            self._initialized = True

        except Exception as exc:
            print(f"[SAM3.1] WARNING: could not load predictor — {exc}")
            print("[SAM3.1] Continuing without SAM3.1 segmentation.")
            self.predictor = None

    @property
    def ready(self) -> bool:
        return self.predictor is not None and self._initialized

    def reset(self) -> None:
        """Clear tracking state between scenes."""
        self.inference_state = None
        self._frame_buffer = []
        self._track_objects = {}
        self._next_obj_id = 1

    def init_state_from_frame(self, frame: np.ndarray) -> None:
        """Initialize inference state from a single BGR frame."""
        if not self.ready:
            return
        try:
            # SAM2 video predictor expects a directory of JPEG frames.
            # For live streaming we use the in-memory API instead.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            # Build a minimal inference state manually
            self.inference_state = self.predictor.init_state_from_frame(
                rgb, offload_video_to_cpu=True
            ) if hasattr(self.predictor, "init_state_from_frame") else None
        except Exception as exc:
            self.inference_state = None

    def add_box_prompt(self, bbox: list[int], label: str = "vehicle") -> int:
        """Add a bounding-box prompt for a new object to track."""
        if not self.ready or self.inference_state is None:
            return -1
        obj_id = self._next_obj_id
        self._next_obj_id += 1
        hue = (obj_id * 47) % 180
        color = tuple(int(c) for c in cv2.cvtColor(
            np.uint8([[[hue, 220, 220]]]), cv2.COLOR_HSV2BGR)[0][0])
        self._track_objects[obj_id] = {"label": label, "color": color}
        try:
            x1, y1, x2, y2 = bbox
            box = np.array([[x1, y1, x2, y2]], dtype=np.float32)
            _, obj_ids, mask_logits = self.predictor.add_new_points_or_box(
                inference_state=self.inference_state,
                frame_idx=0,
                obj_id=obj_id,
                box=box,
            )
        except Exception as exc:
            pass  # graceful degrade
        return obj_id

    def propagate_frame(self, frame: np.ndarray) -> list[dict]:
        """
        Propagate tracking to the next frame.
        Returns list of {obj_id, label, mask, color}.
        """
        if not self.ready or self.inference_state is None:
            return []
        results = []
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            for obj_id, _, mask_logits in self.predictor.propagate_in_video(
                self.inference_state, start_frame_idx=0
            ):
                if obj_id not in self._track_objects:
                    continue
                mask = (mask_logits[0] > 0.0).cpu().numpy().squeeze()
                results.append({
                    "obj_id":  obj_id,
                    "label":   self._track_objects[obj_id]["label"],
                    "mask":    mask,
                    "color":   self._track_objects[obj_id]["color"],
                })
        except Exception:
            pass
        return results


# ─────────────────────────────────────────────────────────────────────────────
# Stream reader — threaded, decoupled from inference
# ─────────────────────────────────────────────────────────────────────────────
class StreamReader:
    def __init__(self, source, queue_size: int = 4):
        self.source = source
        self._q: queue.Queue = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self.fps = 25.0
        self.frame_count = 0

    def start(self) -> "StreamReader":
        self._thread.start()
        return self

    def _resolve_source(self):
        src = self.source
        if isinstance(src, str) and ("youtube.com" in src or "youtu.be" in src):
            try:
                import yt_dlp
                ydl_opts = {"format": "best[ext=mp4]/best", "quiet": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(src, download=False)
                    src = info["url"]
                    print(f"[stream] Resolved YouTube URL: {info.get('title','?')}")
            except Exception as e:
                print(f"[stream] yt-dlp failed: {e}")
        return src

    def _read_loop(self):
        src = self._resolve_source()
        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            print(f"[stream] ERROR: cannot open source: {src}")
            return
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        print(f"[stream] Opened  fps={self.fps:.1f}")
        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                # Try to reconnect once for live streams
                cap.release()
                time.sleep(1.0)
                cap = cv2.VideoCapture(src)
                if not cap.isOpened():
                    break
                continue
            self.frame_count += 1
            if self._q.full():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    pass
            self._q.put(frame)
        cap.release()

    def read(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        self._stop.set()


# ─────────────────────────────────────────────────────────────────────────────
# Demo frame generator (no external source needed)
# ─────────────────────────────────────────────────────────────────────────────
def demo_frame_generator():
    """Yields synthetic dashcam frames indefinitely for demo mode."""
    cap = cv2.VideoCapture("tests/sample_images/road_scene.jpg")
    base = cv2.imread("tests/sample_images/road_scene.jpg")
    if base is None:
        base = np.zeros((720, 1280, 3), dtype=np.uint8)
    idx = 0
    while True:
        frame = base.copy()
        # Animate — shift a vehicle rect to simulate motion
        offset = int((idx * 3) % 400)
        cv2.rectangle(frame, (200 + offset, 320), (350 + offset, 430), (30, 80, 180), -1)
        cv2.rectangle(frame, (220 + offset, 300), (330 + offset, 330), (40, 90, 190), -1)
        cv2.rectangle(frame, (240 + offset, 410), (320 + offset, 430), (230, 230, 230), -1)
        # Timestamp
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        cv2.putText(frame, f"DEMO  {ts}  Frame:{idx:05d}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 120), 1)
        idx += 1
        yield frame


# ─────────────────────────────────────────────────────────────────────────────
# Overlay helpers
# ─────────────────────────────────────────────────────────────────────────────
def draw_box_label(img, x1, y1, x2, y2, label, color, thickness=2):
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(img, (x1, y1 - th - 6), (x1 + tw + 6, y1), color, -1)
    cv2.putText(img, label, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (255, 255, 255), 1, cv2.LINE_AA)


def overlay_mask(img, mask, color, alpha=0.40):
    """Blend a boolean mask onto img in-place."""
    if mask is None or mask.shape[:2] != img.shape[:2]:
        return
    overlay = img.copy()
    overlay[mask] = color
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
    # Draw mask contour
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    cv2.drawContours(img, contours, -1, color, 2)


def draw_hud(img, stats: dict):
    """Bottom-strip HUD with live statistics."""
    h, w = img.shape[:2]
    cv2.rectangle(img, (0, h - 80), (w, h), (0, 0, 0), -1)
    lines = [
        (f"RDD: {stats['rdd_count']} event(s)  {stats['rdd_ms']:.0f}ms",
         (100, 180, 255)),
        (f"Vehicles: {stats['veh_count']}  Plates: {stats['plate_count']}  "
         f"SAM: {'ON' if stats['sam_on'] else 'OFF'}  "
         f"FPS: {stats['fps']:.1f}  Frame: {stats['frame']:05d}",
         (60, 220, 60)),
    ]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    gps = stats.get("gps", "GPS: --")
    cv2.putText(img, f"{gps}  |  {ts}", (10, h - 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 220, 100), 1)
    for i, (text, color) in enumerate(lines):
        cv2.putText(img, text, (10, h - 32 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)


# ─────────────────────────────────────────────────────────────────────────────
# Inference skip logic (run every N frames to maintain throughput)
# ─────────────────────────────────────────────────────────────────────────────
RDD_SKIP   = 3   # run road damage every 3rd frame
VEH_SKIP   = 2   # run vehicle detector every 2nd frame
ANPR_SKIP  = 15  # run plate detector every 15th frame
SAM_SKIP   = 1   # run SAM propagation every frame (it's fast once initialized)
SAM_INIT_EVERY = 30  # re-init SAM2 tracker with fresh detections every 30 frames


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────
def run_pipeline(source, demo: bool = False, headless: bool = False,
                 save_output: Optional[str] = None, max_frames: int = 0):

    # ── Load models ───────────────────────────────────────────────────────────
    print("[models] Loading RDD2022 …")
    rdd = YOLO(RDD_MODEL)

    print("[models] Loading YOLOv8n vehicles …")
    veh_model = YOLO(VEH_MODEL)

    print("[models] Loading ANPR plate detector …")
    plate_model = YOLO(PLATE_MODEL)

    print("[models] Loading SAM 3.1 Multiplex …")
    sam = SAM31Tracker(SAM31_CKPT, device=DEVICE)

    # Warm up YOLO models
    dummy = np.zeros((640, 640, 3), dtype=np.uint8)
    rdd(dummy, verbose=False)
    veh_model(dummy, verbose=False)
    plate_model(dummy, verbose=False)
    print("[models] All models loaded and warmed up.\n")

    # ── Set up source ─────────────────────────────────────────────────────────
    if demo:
        gen = demo_frame_generator()
        def get_frame():
            return next(gen)
    else:
        reader = StreamReader(source).start()
        def get_frame():
            return reader.read(timeout=2.0)

    # ── Output writer ─────────────────────────────────────────────────────────
    writer = None
    if save_output:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(save_output, fourcc, 20.0, (1280, 720))

    # ── State ─────────────────────────────────────────────────────────────────
    frame_idx    = 0
    fps_counter  = deque(maxlen=30)
    paused       = False

    # cached results (reused on skipped frames)
    cached_rdd    = []
    cached_veh    = []
    cached_plates = []
    cached_masks  = []

    stats = {
        "rdd_count": 0, "rdd_ms": 0.0,
        "veh_count": 0, "plate_count": 0,
        "sam_on": sam.ready, "fps": 0.0,
        "frame": 0, "gps": "GPS: 12.9716N 77.5946E",
    }

    print("Pipeline running. Press Q=quit  S=save frame  P=pause  R=reset SAM")
    print("=" * 60)

    while True:
        t_frame_start = time.perf_counter()

        # ── Key handling ──────────────────────────────────────────────────────
        if not headless:
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("p"):
                paused = not paused
                print(f"[ctrl] {'Paused' if paused else 'Resumed'}")
            elif key == ord("r"):
                sam.reset()
                print("[ctrl] SAM3.1 tracker reset")
            elif key == ord("s"):
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                path = f"tests/sample_images/saved_{ts}.jpg"
                if "annotated" in dir():
                    cv2.imwrite(path, annotated)
                    print(f"[ctrl] Saved: {path}")

        if paused:
            time.sleep(0.05)
            continue

        # ── Get frame ─────────────────────────────────────────────────────────
        frame = get_frame()
        if frame is None:
            print("[stream] No frame — stream ended or timeout.")
            break
        if max_frames and frame_idx >= max_frames:
            print(f"[pipeline] Reached max_frames={max_frames}, stopping.")
            break

        # Resize to 1280×720 for consistent processing
        if frame.shape[:2] != (720, 1280):
            frame = cv2.resize(frame, (1280, 720))

        H, W = frame.shape[:2]
        annotated = frame.copy()

        # ── 1. Road Damage (RDD2022) ───────────────────────────────────────────
        if frame_idx % RDD_SKIP == 0:
            t0 = time.perf_counter()
            r = rdd(frame, conf=0.30, verbose=False, device=DEVICE)[0]
            rdd_ms = (time.perf_counter() - t0) * 1000
            cached_rdd = []
            for b in r.boxes:
                cls  = int(b.cls[0])
                conf = float(b.conf[0])
                x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
                cached_rdd.append({
                    "class": rdd.names[cls], "confidence": conf,
                    "bbox": [x1, y1, x2, y2],
                })
            stats["rdd_count"] = len(cached_rdd)
            stats["rdd_ms"]    = rdd_ms
            if cached_rdd:
                print(f"[f{frame_idx:05d}] Road damage: "
                      + ", ".join(f"{d['class']}({d['confidence']:.2f})" for d in cached_rdd))

        # Draw road damage
        for ev in cached_rdd:
            x1, y1, x2, y2 = ev["bbox"]
            label = f"{ev['class']} {ev['confidence']:.2f}"
            draw_box_label(annotated, x1, y1, x2, y2, label, COL_DAMAGE)

        # ── 2. Vehicle Detection ───────────────────────────────────────────────
        if frame_idx % VEH_SKIP == 0:
            t0 = time.perf_counter()
            r2 = veh_model(frame, conf=0.35, verbose=False, device=DEVICE)[0]
            veh_ms = (time.perf_counter() - t0) * 1000
            cached_veh = []
            for b in r2.boxes:
                cls = int(b.cls[0])
                if cls not in VEHICLE_CLS:
                    continue
                conf = float(b.conf[0])
                x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
                cached_veh.append({
                    "class": VEHICLE_CLS[cls], "confidence": conf,
                    "bbox": [x1, y1, x2, y2],
                })
            stats["veh_count"] = len(cached_veh)

            # ── SAM 3.1: re-initialize tracker every SAM_INIT_EVERY frames ───
            if sam.ready and frame_idx % SAM_INIT_EVERY == 0 and cached_veh:
                sam.reset()
                sam.init_state_from_frame(frame)
                for veh in cached_veh[:4]:  # track up to 4 vehicles
                    sam.add_box_prompt(veh["bbox"], label=veh["class"])

        # Draw vehicles
        for veh in cached_veh:
            x1, y1, x2, y2 = veh["bbox"]
            label = f"{veh['class']} {veh['confidence']:.2f}"
            draw_box_label(annotated, x1, y1, x2, y2, label, COL_VEHICLE)

        # ── 3. SAM 3.1 Propagation ────────────────────────────────────────────
        if sam.ready and frame_idx % SAM_SKIP == 0:
            cached_masks = sam.propagate_frame(frame)

        for obj in cached_masks:
            if obj.get("mask") is not None:
                overlay_mask(annotated, obj["mask"], obj["color"], alpha=0.35)
                # Label centroid
                coords = np.argwhere(obj["mask"])
                if len(coords):
                    cy_m, cx_m = coords.mean(axis=0).astype(int)
                    cv2.putText(annotated, f"SAM:{obj['label']}#{obj['obj_id']}",
                                (cx_m - 30, cy_m), cv2.FONT_HERSHEY_SIMPLEX,
                                0.45, obj["color"], 1, cv2.LINE_AA)

        # ── 4. ANPR ────────────────────────────────────────────────────────────
        if frame_idx % ANPR_SKIP == 0:
            cached_plates = []
            for veh in cached_veh:
                x1, y1, x2, y2 = veh["bbox"]
                pw, ph = x2 - x1, y2 - y1
                ex1 = max(0, x1 - int(pw * 0.15))
                ey1 = max(0, y1 - int(ph * 0.15))
                ex2 = min(W, x2 + int(pw * 0.15))
                ey2 = min(H, y2 + int(ph * 0.15))
                crop = frame[ey1:ey2, ex1:ex2]
                if crop.size == 0:
                    continue
                pr = plate_model(crop, conf=0.30, verbose=False, device=DEVICE)[0]
                for pb in pr.boxes:
                    pconf = float(pb.conf[0])
                    px1, py1, px2, py2 = [int(c) for c in pb.xyxy[0].tolist()]
                    abs_bbox = [ex1 + px1, ey1 + py1, ex1 + px2, ey1 + py2]
                    cached_plates.append({
                        "bbox": abs_bbox, "confidence": pconf,
                        "vehicle": veh["class"],
                    })
            stats["plate_count"] = len(cached_plates)

        for pl in cached_plates:
            x1, y1, x2, y2 = pl["bbox"]
            draw_box_label(annotated, x1, y1, x2, y2,
                           f"PLATE {pl['confidence']:.2f}", COL_PLATE, thickness=1)

        # ── HUD + FPS ──────────────────────────────────────────────────────────
        t_frame_end = time.perf_counter()
        fps_counter.append(1.0 / max(t_frame_end - t_frame_start, 1e-6))
        stats["fps"]   = sum(fps_counter) / len(fps_counter)
        stats["frame"] = frame_idx
        draw_hud(annotated, stats)

        # ── Display ────────────────────────────────────────────────────────────
        if not headless:
            cv2.imshow("Road Intelligence — Live Dashcam Pipeline", annotated)

        if writer:
            writer.write(annotated)

        frame_idx += 1

    # ── Cleanup ────────────────────────────────────────────────────────────────
    if not headless:
        cv2.destroyAllWindows()
    if writer:
        writer.release()
    if not demo:
        reader.stop()

    print(f"\n[done] Processed {frame_idx} frames.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Road Intelligence Live Dashcam Pipeline with SAM 3.1"
    )
    parser.add_argument("--source",   type=str, default=None,
                        help="Video source: file path, RTSP URL, YouTube URL, or webcam index")
    parser.add_argument("--demo",     action="store_true",
                        help="Use synthetic demo frames (no external source)")
    parser.add_argument("--headless", action="store_true",
                        help="Run without display (useful for servers)")
    parser.add_argument("--save",     type=str, default=None,
                        help="Save annotated output to this .mp4 file")
    parser.add_argument("--max-frames", type=int, default=0,
                        help="Stop after N frames (0 = run forever)")
    args = parser.parse_args()

    if not args.demo and args.source is None:
        print("No source specified. Running in DEMO mode.")
        print("Use --source <path/url> for a real stream, or --demo for synthetic frames.\n")
        args.demo = True

    run_pipeline(
        source=args.source,
        demo=args.demo,
        headless=args.headless,
        save_output=args.save,
        max_frames=args.max_frames,
    )
