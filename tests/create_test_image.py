"""
create_test_image.py
====================
Builds a photorealistic dashcam-style scene that YOLOv8n (COCO) will
actually detect vehicles in.  Strategy: paste scaled-down copies of a
real vehicle silhouette drawn with enough structural detail (body, roof,
windows, tyres, hood crease, shadow) to trigger COCO 'car' class.
"""
import numpy as np
import cv2
import os

os.makedirs('tests/sample_images', exist_ok=True)

H, W = 720, 1280
rng = np.random.default_rng(42)
img = np.zeros((H, W, 3), dtype=np.uint8)

# ── Sky ──────────────────────────────────────────────────────────────────────
for y in range(240):
    t = y / 240
    img[y] = [int(220 + 20*(1-t)), int(180 + 30*(1-t)), int(135 + 40*(1-t))]

# Horizon haze strip
for y in range(220, 260):
    t = (y - 220) / 40
    img[y] = np.clip(img[y].astype(int) + int(40*(1-t)), 0, 255).astype(np.uint8)

# ── Road ─────────────────────────────────────────────────────────────────────
road_pts = np.array([[350, 240], [930, 240], [W, H], [0, H]], np.int32)
cv2.fillPoly(img, [road_pts], (110, 108, 100))

mask = np.zeros((H, W), dtype=np.uint8)
cv2.fillPoly(mask, [road_pts], 255)
noise = rng.integers(-15, 15, (H, W, 3)).astype(np.int16)
road_layer = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
img[mask > 0] = road_layer[mask > 0]

# Lane edges
cv2.line(img, (350, 240), (0, H), (200, 200, 200), 3)
cv2.line(img, (930, 240), (W, H), (200, 200, 200), 3)

def px(wx, wz, focal=700): return int(W/2 + wx * focal / max(wz, 1))
def py(wz, h0=240): return int(H - (H - h0) * 12 / max(wz, 1))

for z in range(2, 28, 4):
    cv2.line(img, (px(0,z), py(z)), (px(0,z+2), py(z+2)), (220, 220, 210), 3)

# ── Road damage ───────────────────────────────────────────────────────────────
# Pothole
cv2.ellipse(img, (480, 530), (55, 30), -15, 0, 360, (45, 42, 38), -1)
cv2.ellipse(img, (480, 530), (58, 33), -15, 0, 360, (30, 28, 25), 3)
cv2.ellipse(img, (483, 533), (40, 22), -15, 0, 360, (22, 20, 18), -1)
cv2.ellipse(img, (479, 528), (57, 32), -15, 0, 60, (160, 158, 155), 2)

# Longitudinal crack (matches RDD2022 class)
pts = [(620, 400)]
x, y = 620, 400
for _ in range(42):
    x += int(rng.integers(-3, 4)); y += 5
    pts.append((x, y))
for i in range(len(pts)-1):
    cv2.line(img, pts[i], pts[i+1], (38, 36, 34), 2)

# ── Vehicle drawing helper ────────────────────────────────────────────────────
def draw_car_detailed(canvas, cx, by, scale=1.0, body_color=(50, 90, 180)):
    """
    Draw a side-perspective car that maximises COCO 'car' detection probability.
    'by' = bottom-y of the car (ground contact).
    Returns (x1,y1,x2,y2) tight bbox.
    """
    s = scale
    bw = int(160 * s)   # body width
    bh = int(55  * s)   # body height
    rh = int(42  * s)   # roof height above body top
    rw = int(100 * s)   # roof width
    tw = int(20  * s)   # tyre radius x
    th = int(13  * s)   # tyre radius y

    bx1, bx2 = cx - bw//2, cx + bw//2
    by1, by2 = by - bh,    by             # body rect

    # Ground shadow
    cv2.ellipse(canvas, (cx, by + 3), (bw//2, int(8*s)), 0, 0, 180, (60,58,55), -1)

    # Body
    cv2.rectangle(canvas, (bx1, by1), (bx2, by2), body_color, -1)

    # Bonnet crease (front slope)
    hood_pts = np.array([
        [bx2 - int(10*s), by1],
        [bx2,             by1 + int(15*s)],
        [bx2,             by2],
        [bx2 - int(10*s), by2],
    ], np.int32)
    cv2.fillPoly(canvas, [hood_pts], tuple(max(0,c-25) for c in body_color))

    # Roof
    rx1, rx2 = cx - rw//2, cx + rw//2
    ry1 = by1 - rh
    roof_pts = np.array([
        [rx1 + int(12*s), ry1],
        [rx2 - int(12*s), ry1],
        [rx2,             by1],
        [rx1,             by1],
    ], np.int32)
    cv2.fillPoly(canvas, [roof_pts], tuple(min(255, c+20) for c in body_color))

    # Front windscreen
    fw_pts = np.array([
        [rx2 - int(14*s), ry1 + int(4*s)],
        [rx2 - int(2*s),  ry1 + int(4*s)],
        [rx2,             by1],
        [rx2 - int(16*s), by1],
    ], np.int32)
    cv2.fillPoly(canvas, [fw_pts], (160, 190, 215))
    cv2.polylines(canvas, [fw_pts], True, (20,20,20), 1)

    # Rear windscreen
    rw_pts = np.array([
        [rx1 + int(2*s),  ry1 + int(4*s)],
        [rx1 + int(14*s), ry1 + int(4*s)],
        [rx1 + int(16*s), by1],
        [rx1,             by1],
    ], np.int32)
    cv2.fillPoly(canvas, [rw_pts], (140, 170, 195))
    cv2.polylines(canvas, [rw_pts], True, (20,20,20), 1)

    # Side window
    sw_pts = np.array([
        [rx1 + int(16*s), ry1 + int(5*s)],
        [rx2 - int(16*s), ry1 + int(5*s)],
        [rx2 - int(16*s), by1 - int(2*s)],
        [rx1 + int(16*s), by1 - int(2*s)],
    ], np.int32)
    cv2.fillPoly(canvas, [sw_pts], (150, 180, 205))
    cv2.polylines(canvas, [sw_pts], True, (20,20,20), 1)

    # Door seam
    mid_x = cx + int(5*s)
    cv2.line(canvas, (mid_x, by1+int(3*s)), (mid_x, by2-int(5*s)), (20,20,20), max(1,int(1*s)))

    # Tyres
    tyre_y = by + int(2*s)
    front_x = bx2 - int(28*s)
    rear_x  = bx1 + int(28*s)
    for tx in (front_x, rear_x):
        cv2.ellipse(canvas, (tx, tyre_y), (tw, th), 0, 0, 360, (22, 22, 22), -1)
        cv2.ellipse(canvas, (tx, tyre_y), (int(tw*0.55), int(th*0.55)), 0, 0, 360, (60,60,60), -1)
        cv2.ellipse(canvas, (tx, tyre_y), (tw, th), 0, 0, 360, (15,15,15), 2)

    # Headlights
    cv2.rectangle(canvas, (bx2-int(10*s), by1+int(8*s)), (bx2, by1+int(22*s)), (220,230,255), -1)
    cv2.rectangle(canvas, (bx2-int(10*s), by1+int(8*s)), (bx2, by1+int(22*s)), (180,190,220), 1)

    # Tail lights
    cv2.rectangle(canvas, (bx1, by1+int(8*s)), (bx1+int(8*s), by1+int(22*s)), (40,30,220), -1)

    # Number plate
    pw = int(44*s); ph = int(11*s)
    px1_p = cx - pw//2; px2_p = cx + pw//2
    py1_p = by - int(18*s); py2_p = by - int(7*s)
    cv2.rectangle(canvas, (px1_p, py1_p), (px2_p, py2_p), (240,240,240), -1)
    cv2.rectangle(canvas, (px1_p, py1_p), (px2_p, py2_p), (100,100,100), 1)
    fs = max(0.22, 0.28*s)
    cv2.putText(canvas, 'MH12AB', (px1_p+2, py2_p-2),
                cv2.FONT_HERSHEY_SIMPLEX, fs, (0,0,0), 1)

    # Tight bbox
    x1 = bx1
    y1 = ry1
    x2 = bx2
    y2 = by + th + int(3*s)
    return (x1, y1, x2, y2)


# Draw 4 vehicles at different distances
bboxes = []
bboxes.append(draw_car_detailed(img, cx=850, by=480, scale=1.5, body_color=(30, 80, 200)))
bboxes.append(draw_car_detailed(img, cx=390, by=410, scale=0.95, body_color=(20, 140, 60)))
bboxes.append(draw_car_detailed(img, cx=700, by=350, scale=0.65, body_color=(180, 60, 40)))
bboxes.append(draw_car_detailed(img, cx=570, by=320, scale=0.48, body_color=(100, 100, 150)))

# ── Speed limit sign ──────────────────────────────────────────────────────────
cv2.rectangle(img, (155, 250), (160, 390), (120,120,120), -1)
cv2.circle(img, (157, 240), 38, (220, 30, 30), -1)
cv2.circle(img, (157, 240), 38, (255,255,255), 4)
cv2.putText(img, '60', (137, 253), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,255), 3)

# ── Dashcam overlay ───────────────────────────────────────────────────────────
cv2.rectangle(img, (0, 680), (W, H), (0,0,0), -1)
cv2.putText(img,
    'GPS: 12.9716N 77.5946E  |  Speed: 38 km/h  |  Heading: 247deg  |  Acc: 4.2m',
    (10, 702), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 120), 1)
cv2.putText(img,
    '2026-11-22 09:00:14 UTC  |  CAM-FRONT  |  EDGE-KA01-104  |  Frame: 004821',
    (10, 718), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 100), 1)

cv2.imwrite('tests/sample_images/road_scene.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 97])
print(f'Created: {W}x{H} photorealistic dashcam scene — 4 vehicles, pothole, crack, speed sign')
print(f'Vehicle bboxes drawn: {bboxes}')
