# Baseline model weights

This directory holds local inference checkpoints and is intentionally excluded from source control by the repository `.gitignore`.

| File | Purpose | Status |
| --- | --- | --- |
| `rdd2022-yolov8s-best.pt` | Road-damage detector for potholes and three crack types | downloaded |
| SAM 3.1 checkpoint | Candidate mask refinement and video tracking | gated: user access approval required |
| `road-defects-india-v1.pt` | Fine-tuned pothole, crack, speed-breaker, waterlogging and construction detector | training artifact — not yet available |

`rdd2022-yolov8s-best.pt` is the primary detector. Its classes are longitudinal crack, transverse crack, alligator crack, and pothole; it cannot detect speed breakers, standing water, construction, or road signs. Run SAM 3.1 as an on-demand second stage for segmentation/tracking after access is approved. Before production, train `road-defects-india-v1.pt` from a licensed, consented dataset that includes local lighting, monsoon, camera vibration, and mixed-traffic conditions; evaluate it separately by class and geography.

Use the dependencies from the Ultralytics documentation to load these checkpoints. Preserve the exact source URL and SHA-256 in `manifest.json` after each download.
