"""
make_photo_car.py — render a photographic-quality car and test YOLOv8n on it.
"""
import cv2
import numpy as np
import os


def make_photo_car(w, h, body_rgb, metallic=True):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (108, 105, 100)

    bx1, bx2 = int(w*0.08), int(w*0.92)
    by1, by2 = int(h*0.42), int(h*0.78)
    cv2.rectangle(img, (bx1, by1), (bx2, by2), body_rgb, -1)
    for i in range(by2 - by1):
        t = i / (by2 - by1)
        blend = int(40*(1-t) - 20*t)
        row = img[by1+i, bx1:bx2].astype(int)
        img[by1+i, bx1:bx2] = np.clip(row + blend, 0, 255).astype(np.uint8)

    rx1, rx2 = int(w*0.18), int(w*0.82)
    ry1, ry2 = int(h*0.14), int(h*0.44)
    roof_pts = np.array([[rx1+int(w*0.08), ry1], [rx2-int(w*0.08), ry1], [rx2, ry2], [rx1, ry2]], np.int32)
    cv2.fillPoly(img, [roof_pts], tuple(min(255, c+15) for c in body_rgb))

    wf = np.array([
        [rx2-int(w*0.06), ry1+int(h*0.04)],
        [rx2-int(w*0.01), ry1+int(h*0.04)],
        [rx2,              ry2],
        [rx2-int(w*0.14), ry2],
    ], np.int32)
    cv2.fillPoly(img, [wf], (145, 175, 195))
    cv2.polylines(img, [wf], True, (15, 15, 15), 2)
    overlay = img.copy()
    gp = wf + np.array([[int(w*0.02), int(h*0.02)], [-int(w*0.04), int(h*0.02)],
                         [-int(w*0.04), -int(h*0.06)], [int(w*0.02), -int(h*0.06)]], np.int32)
    cv2.fillPoly(overlay, [gp], (200, 220, 235))
    cv2.addWeighted(overlay, 0.25, img, 0.75, 0, img)

    wr_pts = np.array([
        [rx1+int(w*0.01), ry1+int(h*0.04)],
        [rx1+int(w*0.06), ry1+int(h*0.04)],
        [rx1+int(w*0.14), ry2],
        [rx1,              ry2],
    ], np.int32)
    cv2.fillPoly(img, [wr_pts], (120, 155, 175))
    cv2.polylines(img, [wr_pts], True, (15, 15, 15), 2)

    sw_pts = np.array([
        [rx1+int(w*0.14), ry1+int(h*0.05)],
        [rx2-int(w*0.14), ry1+int(h*0.05)],
        [rx2-int(w*0.14), ry2-int(h*0.02)],
        [rx1+int(w*0.14), ry2-int(h*0.02)],
    ], np.int32)
    cv2.fillPoly(img, [sw_pts], (135, 165, 185))
    cv2.polylines(img, [sw_pts], True, (15, 15, 15), 1)
    mp = int(w*0.5)
    cv2.rectangle(img, (mp-int(w*0.015), ry1+int(h*0.04)), (mp+int(w*0.015), ry2), (20, 20, 20), -1)

    hood_pts = np.array([
        [bx2-int(w*0.14), by1],
        [bx2,              by1+int(h*0.1)],
        [bx2,              by2],
        [bx2-int(w*0.08), by2],
    ], np.int32)
    cv2.fillPoly(img, [hood_pts], tuple(max(0, c-30) for c in body_rgb))

    hl_x = bx2 - int(w*0.09)
    for dy in range(2):
        y_c = by1 + int(h*0.07) + dy*int(h*0.08)
        cv2.ellipse(img, (hl_x, y_c), (int(w*0.055), int(h*0.04)), 0, 0, 360, (230, 235, 255), -1)
        cv2.ellipse(img, (hl_x, y_c), (int(w*0.03),  int(h*0.025)),0, 0, 360, (255, 255, 210), -1)
        cv2.ellipse(img, (hl_x, y_c), (int(w*0.055), int(h*0.04)), 0, 0, 360, (160, 165, 185), 1)

    tl_x = bx1 + int(w*0.06)
    cv2.ellipse(img, (tl_x, by1+int(h*0.1)), (int(w*0.04), int(h*0.06)), 0, 0, 360, (50, 30, 200), -1)
    cv2.ellipse(img, (tl_x, by1+int(h*0.1)), (int(w*0.04), int(h*0.06)), 0, 0, 360, (30, 15, 160), 2)

    gx1, gx2 = bx2-int(w*0.14), bx2
    gy1, gy2 = by1+int(h*0.18), by2-int(h*0.12)
    cv2.rectangle(img, (gx1, gy1), (gx2, gy2), (30, 30, 30), -1)
    for gly in range(gy1+4, gy2, 8):
        cv2.line(img, (gx1, gly), (gx2, gly), (70, 70, 70), 1)

    cv2.rectangle(img, (bx1, by2-int(h*0.08)), (bx2, by2+int(h*0.04)), (80, 80, 88), -1)
    cv2.rectangle(img, (bx1, by2-int(h*0.08)), (bx2, by2+int(h*0.04)), (50, 50, 55), 2)

    px1 = bx2-int(w*0.14); px2 = bx2-int(w*0.03)
    py1 = by2-int(h*0.07); py2 = by2-int(h*0.01)
    cv2.rectangle(img, (px1, py1), (px2, py2), (240, 240, 240), -1)
    cv2.rectangle(img, (px1, py1), (px2, py2), (80, 80, 80), 1)
    cv2.putText(img, 'MH12AB', (px1+3, py2-3), cv2.FONT_HERSHEY_SIMPLEX,
                max(0.3, (px2-px1)/85.0), (0, 0, 0), 1)

    wy = by2 + int(h*0.02)
    wr_rx, wr_ry = int(w*0.11), int(h*0.09)
    for wx_c in (bx1+int(w*0.18), bx2-int(w*0.18)):
        cv2.ellipse(img, (wx_c, wy), (wr_rx, wr_ry), 0, 0, 360, (22, 22, 22), -1)
        cv2.ellipse(img, (wx_c, wy), (int(wr_rx*0.7), int(wr_ry*0.7)), 0, 0, 360, (180, 180, 180), -1)
        cv2.ellipse(img, (wx_c, wy), (int(wr_rx*0.25), int(wr_ry*0.25)), 0, 0, 360, (120, 120, 120), -1)
        for a in range(0, 360, 72):
            rad = np.deg2rad(a)
            ex_x = int(wx_c + wr_rx*0.65*np.cos(rad))
            ex_y = int(wy   + wr_ry*0.65*np.sin(rad))
            cv2.line(img, (wx_c, wy), (ex_x, ex_y), (90, 90, 90), 2)
        cv2.ellipse(img, (wx_c, wy), (wr_rx, wr_ry), 0, 0, 360, (10, 10, 10), 2)

    ov = img.copy()
    cv2.ellipse(ov, (int(w*0.5), by2+int(h*0.08)), (int(w*0.4), int(h*0.04)), 0, 0, 360, (65, 62, 58), -1)
    cv2.addWeighted(ov, 0.6, img, 0.4, 0, img)

    img = cv2.GaussianBlur(img, (3, 3), 0.8)
    noise = np.random.normal(0, 4, img.shape).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return img


if __name__ == '__main__':
    os.makedirs('tests/sample_images', exist_ok=True)
    c1 = make_photo_car(320, 220, (30, 80, 200))
    cv2.imwrite('tests/sample_images/car_test.jpg', c1, [cv2.IMWRITE_JPEG_QUALITY, 97])
    print('Car test image saved')

    from ultralytics import YOLO
    model = YOLO('services/parking_anpr/models/yolov8n.pt')
    VEHICLE_CLASSES = {2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}
    r = model(c1, conf=0.10, verbose=False, device='cuda')[0]
    for b in r.boxes:
        cls = int(b.cls[0])
        conf = float(b.conf[0])
        print(f'  cls={cls} ({model.names[cls]:20s})  conf={conf:.3f}')
    print(f'Vehicle detections: {sum(1 for b in r.boxes if int(b.cls[0]) in VEHICLE_CLASSES)}')
