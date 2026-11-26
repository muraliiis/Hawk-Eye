# Licensed Dashcam Replay

The Driver HUD can replay a local video selected by the user. It samples the video at 0.5 FPS and sends only transient JPEG frames to `/api/perception/replay-frame` for road-defect inference.

Privacy and retention rules:

- the original video remains in the browser and is never uploaded;
- frame bytes are decoded in memory and explicitly discarded after inference;
- only normalized `RoadEvent` metadata is published to the event stream;
- duplicate detections of the same class on the same road segment are throttled for 15 seconds;
- the flow is for footage that the user owns or is authorized to process.

The replay detector currently uses `models/rdd2022-yolov8s-best.pt`. It recognizes potholes plus longitudinal, transverse, and alligator cracks; the crack variants are normalized to the shared `crack` event category and retained in the event attributes as `source_label`.

## Running locally

1. Place the checkpoint at `models/rdd2022-yolov8s-best.pt`.
2. Install `backend/requirements.txt` and start the backend from `backend/` with `uvicorn main:app --reload --port 8000`.
3. Start `apps/user-app` with `npm run dev`.
4. In the **Dashcam** tab, select **Load Licensed Video**, map it to the appropriate road segment, and select **Start Replay**.

For Docker Compose, the checkpoint is mounted read-only into the backend container at `/app/models`.
