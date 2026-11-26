"""
generate_dashcam_video.py
=========================
Generate a photorealistic synthetic dashcam video with:
- Road perspective with asphalt texture
- Moving vehicles (cars, motorcycles)
- Visible potholes and cracks (detectable by RDD2022)
- License plates on vehicles
- Day/night variation
- Camera vibration simulation
- GPS/timestamp HUD overlay

Outputs: tests/sample_images/dashcam_synthetic.mp4  (600 frames @ 30fps = 20s)
"""
import cv2
import numpy as np
import os

os.makedirs("tests/sample_images", exist_ok=True)

# ── Video parameters ──────────────────────────────────────────────────────────
W, H   = 1280, 720
FPS    = 30
FRAMES = 600          # 20 seconds
OUT    = "tests/sample_images/dashcam_synthetic.mp4"
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = cv2.VideoWriter(OUT, fourcc, FPS, (W, H))

# ── Noise texture cache ───────────────────────────────────────────────────────
rng = np.random.default_rng(42)

def asphalt_texture(h, w, seed=0):
    """Generate a tileable asphalt noise texture."""
    r = np.random.RandomState(seed)
    base = r.randint(75, 105, (h, w, 3)).astype(np.uint8)
    # Add gravel-like high-freq noise
    noise = r.randint(-20, 20, (h, w, 3))
    return np.clip(base.astype(int) + noise, 55, 115).astype(np.uint8)

ASPHALT = asphalt_texture(H, W)

# ── Road geometry (vanishing point perspective) ───────────────────────────────
VP_X, VP_Y = W // 2, int(H * 0.38)   # vanishing point

def road_x_at_y(lane_offset_norm: float, y: int) -> int:
    """Convert normalized lane offset [-1..1] to pixel x at row y."""
    half_width_at_y = max(1, (y - VP_Y)) * 2.1
    return int(VP_X + lane_offset_norm * half_width_at_y)

# ── Sky gradient ──────────────────────────────────────────────────────────────
SKY = np.zeros((H, W, 3), dtype=np.uint8)
for y in range(H):
    t = min(1.0, y / (VP_Y + 30))
    SKY[y] = [int(220 - 60 * t), int(200 - 40 * t), int(170 - 20 * t)]

# ── Vehicle sprites ───────────────────────────────────────────────────────────
def draw_vehicle(canvas, cx, cy, scale, color, plate_text=""):
    """Draw a simple perspective vehicle."""
    bw = int(80 * scale)
    bh = int(45 * scale)
    # Body
    cv2.rectangle(canvas, (cx - bw//2, cy - bh//4), (cx + bw//2, cy + bh//2), color, -1)
    # Cabin
    cw = int(bw * 0.55)
    cv2.rectangle(canvas, (cx - cw//2, cy - bh*3//4), (cx + cw//2, cy - bh//4),
                  tuple(min(255, c + 25) for c in color), -1)
    # Window
    ww = int(cw * 0.7)
    cv2.rectangle(canvas, (cx - ww//2, cy - bh*2//3), (cx + ww//2, cy - bh//3),
                  (155, 185, 210), -1)
    # Wheels
    r = max(2, int(13 * scale))
    cv2.ellipse(canvas, (cx - bw//3, cy + bh//2), (r, r//2), 0, 0, 360, (22, 22, 22), -1)
    cv2.ellipse(canvas, (cx + bw//3, cy + bh//2), (r, r//2), 0, 0, 360, (22, 22, 22), -1)
    # Headlight / tail light
    cv2.rectangle(canvas, (cx + bw//2 - 8, cy), (cx + bw//2, cy + bh//5),
                  (220, 230, 250), -1)
    # License plate
    if plate_text and scale > 0.5:
        pw, ph = max(30, int(38 * scale)), max(8, int(10 * scale))
        px1, py1 = cx - pw//2, cy + bh//4
        cv2.rectangle(canvas, (px1, py1), (px1 + pw, py1 + ph), (240, 240, 240), -1)
        cv2.rectangle(canvas, (px1, py1), (px1 + pw, py1 + ph), (0, 0, 0), 1)
        font_scale = max(0.22, 0.28 * scale)
        cv2.putText(canvas, plate_text, (px1 + 2, py1 + ph - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 1)

# ── Pothole renderer ──────────────────────────────────────────────────────────
def draw_pothole(canvas, cx, cy, rx, ry, angle=0):
    """Draw a realistic pothole with shadow and depth."""
    # Shadow ring
    cv2.ellipse(canvas, (cx + 3, cy + 3), (rx + 4, ry + 3), angle, 0, 360, (25, 23, 20), -1)
    # Main pit
    cv2.ellipse(canvas, (cx, cy), (rx, ry), angle, 0, 360, (40, 38, 35), -1)
    # Inner dark
    cv2.ellipse(canvas, (cx, cy), (max(1, rx - 8), max(1, ry - 5)), angle, 0, 360, (18, 16, 13), -1)
    # Highlight (water reflection sim)
    cv2.ellipse(canvas, (cx - rx//4, cy - ry//4), (rx//5, ry//5), angle, 0, 360, (90, 88, 85), -1)

# ── Crack renderer ────────────────────────────────────────────────────────────
def draw_crack(canvas, start_x, start_y, length, direction="v", width=2):
    """Draw a jagged crack line."""
    x, y = start_x, start_y
    pts = [(x, y)]
    steps = length // 4
    for _ in range(steps):
        if direction == "v":
            y += 4 + np.random.randint(0, 3)
            x += np.random.randint(-3, 4)
        else:
            x += 4 + np.random.randint(0, 3)
            y += np.random.randint(-3, 4)
        pts.append((x, y))
    for i in range(len(pts) - 1):
        cv2.line(canvas, pts[i], pts[i+1], (38, 36, 33), width)

# ── Vehicle state (position, speed, lane) ────────────────────────────────────
class Vehicle:
    def __init__(self, lane, z, speed, color, plate):
        self.lane  = lane     # normalized lateral position [-0.9..0.9]
        self.z     = z        # depth: 1=far, 60=close
        self.speed = speed    # z-units per frame
        self.color = color
        self.plate = plate

    def update(self):
        self.z += self.speed
        if self.z > 65:
            # Respawn far away
            self.z = np.random.uniform(5, 15)
            self.lane = np.random.choice([-0.45, -0.15, 0.15, 0.45])

    def to_screen(self):
        scale = max(0.1, min(2.0, self.z / 30.0))
        y = int(VP_Y + (H - VP_Y) * (1 - 15.0 / max(self.z, 1)))
        x = road_x_at_y(self.lane, y)
        return x, y, scale

VEHICLES = [
    Vehicle(-0.45, 20, 0.8, (30, 80, 200),  "MH12AB1234"),
    Vehicle( 0.45, 30, 0.6, (20, 140, 60),  "KA05CD5678"),
    Vehicle(-0.15, 12, 1.2, (160, 50, 40),  "DL3EF9012"),
    Vehicle( 0.15, 45, 0.4, (120, 100, 180),"TN07GH3456"),
    Vehicle(-0.45, 55, 0.3, (200, 160, 20), "MH01IJ7890"),
]

# ── Fixed road hazards ────────────────────────────────────────────────────────
# Potholes at fixed road coordinates (lane, depth_z)
POTHOLES = [
    (-0.3, 25),   # left of centre
    ( 0.2, 38),   # right lane
    (-0.1, 18),   # near-centre
]
CRACKS = [
    (-0.5, 22, "v"),
    ( 0.4, 32, "v"),
    ( 0.0, 28, "h"),
]

# ── GPS simulation ────────────────────────────────────────────────────────────
gps_lat  = 12.9716
gps_lon  = 77.5946
gps_spd  = 38.0
GPS_DRIFT = 0.00002

print(f"Generating {FRAMES} frames @ {FPS}fps ({FRAMES/FPS:.0f}s)…")

for fidx in range(FRAMES):
    # Base frame = sky + asphalt road
    frame = SKY.copy()

    # Road surface — full trapezoid covering entire lower half
    road_pts = np.array([
        [road_x_at_y(-1.0, VP_Y + 5), VP_Y + 5],
        [road_x_at_y( 1.0, VP_Y + 5), VP_Y + 5],
        [W, H], [0, H]
    ], dtype=np.int32)
    # Clamp to screen edges
    road_pts[:, 0] = np.clip(road_pts[:, 0], 0, W - 1)
    cv2.fillPoly(frame, [road_pts], (88, 90, 95))

    # Asphalt texture overlay (road region only)
    road_mask = np.zeros((H, W), dtype=np.uint8)
    cv2.fillPoly(road_mask, [road_pts], 255)
    tex_blend = cv2.addWeighted(frame, 0.25, ASPHALT, 0.75, 0)
    frame[road_mask > 0] = tex_blend[road_mask > 0]

    # Fill any remaining black strips on edges with road colour
    frame[VP_Y + 5:, 0:50]  = (85, 88, 92)
    frame[VP_Y + 5:, W-50:] = (85, 88, 92)

    # Lane markings (perspective-correct dashes)
    for lane_off in [-0.0]:  # centre line
        for step in range(0, 25, 4):
            z1, z2 = step + 2, step + 4
            y1 = int(VP_Y + (H - VP_Y) * (1 - 15.0 / max(z1, 1)))
            y2 = int(VP_Y + (H - VP_Y) * (1 - 15.0 / max(z2, 1)))
            x1 = road_x_at_y(lane_off, y1)
            x2 = road_x_at_y(lane_off, y2)
            if VP_Y < y1 < H and VP_Y < y2 < H:
                cv2.line(frame, (x1, y1), (x2, y2), (220, 220, 220), 2)

    # Edge lines
    el1 = [(road_x_at_y(-0.9, y), y) for y in range(VP_Y + 5, H, 8)]
    el2 = [(road_x_at_y( 0.9, y), y) for y in range(VP_Y + 5, H, 8)]
    for pts in [el1, el2]:
        for i in range(len(pts) - 1):
            cv2.line(frame, pts[i], pts[i+1], (200, 200, 200), 2)

    # ── Potholes ──────────────────────────────────────────────────────────────
    for (lane, z_pot) in POTHOLES:
        y_p = int(VP_Y + (H - VP_Y) * (1 - 15.0 / max(z_pot, 1)))
        x_p = road_x_at_y(lane, y_p)
        scale = max(0.1, z_pot / 30.0)
        rx = max(3, int(42 * scale * 0.6))
        ry = max(2, int(26 * scale * 0.5))
        if VP_Y + 10 < y_p < H - 10:
            draw_pothole(frame, x_p, y_p, rx, ry, angle=int(fidx * 0.1) % 180)

    # ── Cracks ────────────────────────────────────────────────────────────────
    for (lane, z_cr, direction) in CRACKS:
        y_c = int(VP_Y + (H - VP_Y) * (1 - 15.0 / max(z_cr, 1)))
        x_c = road_x_at_y(lane, y_c)
        scale = max(0.1, z_cr / 30.0)
        length = max(10, int(80 * scale))
        if VP_Y + 10 < y_c < H - 20:
            draw_crack(frame, x_c, y_c, length, direction, width=max(1, int(2 * scale)))

    # ── Vehicles (sort by z desc = far first) ─────────────────────────────────
    for veh in sorted(VEHICLES, key=lambda v: -v.z):
        x, y, scale = veh.to_screen()
        if VP_Y + 5 < y < H - 5 and 0 < x < W:
            draw_vehicle(frame, x, y, scale, veh.color, veh.plate)
        veh.update()

    # ── Speed limit sign ──────────────────────────────────────────────────────
    if fidx % 150 < 90:
        sign_x, sign_y = 115, 290
        cv2.rectangle(frame, (sign_x, sign_y + 30), (sign_x + 5, sign_y + 110), (130, 130, 130), -1)
        cv2.circle(frame, (sign_x + 2, sign_y), 32, (200, 30, 30), -1)
        cv2.circle(frame, (sign_x + 2, sign_y), 32, (255, 255, 255), 3)
        cv2.putText(frame, "60", (sign_x - 18, sign_y + 11),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    # ── Camera vibration simulation ───────────────────────────────────────────
    vib = 1 if fidx > 0 else 0
    if vib:
        dx = int(np.random.normal(0, 1.5))
        dy = int(np.random.normal(0, 1.0))
        M  = np.float32([[1, 0, dx], [0, 1, dy]])
        frame = cv2.warpAffine(frame, M, (W, H))

    # ── GPS drift ─────────────────────────────────────────────────────────────
    gps_lat += GPS_DRIFT * np.random.uniform(-1, 1)
    gps_lon += GPS_DRIFT * 0.8
    gps_spd  = 38.0 + np.random.normal(0, 1.5)

    # ── HUD overlay ───────────────────────────────────────────────────────────
    cv2.rectangle(frame, (0, H - 42), (W, H), (0, 0, 0), -1)
    hud1 = (f"GPS: {gps_lat:.5f}N {gps_lon:.5f}E  "
            f"Speed: {gps_spd:.1f}km/h  Heading: 247°  Acc: 4.2m")
    hud2 = (f"2026-11-22 09:{(fidx//FPS)//60:02d}:{(fidx//FPS)%60:02d} UTC  "
            f"CAM-FRONT  EDGE-KA01-104  Frame:{fidx:05d}")
    cv2.putText(frame, hud1, (10, H - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 120), 1)
    cv2.putText(frame, hud2, (10, H - 8),  cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 200, 100), 1)

    writer.write(frame)

    if fidx % 60 == 0:
        pct = fidx / FRAMES * 100
        print(f"  {fidx}/{FRAMES} frames ({pct:.0f}%)…")

writer.release()
size_mb = os.path.getsize(OUT) / 1e6
print(f"\nDone! {OUT}  ({size_mb:.1f} MB)")

# Save 3 sample frames
cap = cv2.VideoCapture(OUT)
for i, pos in enumerate([50, 200, 450]):
    cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
    ok, f = cap.read()
    if ok:
        cv2.imwrite(f"tests/sample_images/synth_frame_{i}.jpg", f)
cap.release()
print("Sample frames saved: synth_frame_0/1/2.jpg")
print(f"\nRun live pipeline:")
print(f"  python tests/live_dashcam_pipeline.py --source {OUT} --headless --max-frames 300 --save tests/sample_images/dashcam_annotated.mp4")
