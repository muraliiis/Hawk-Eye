"""
search_and_get_dashcam.py
=========================
Use yt-dlp's YouTube search to find and download a real road dashcam video.
"""
import yt_dlp, os, cv2, sys

os.makedirs("tests/sample_images", exist_ok=True)
DEST = "tests/sample_images/dashcam_clip.mp4"

SEARCH_QUERIES = [
    "ytsearch3:Indian road dashcam pothole 2024",
    "ytsearch3:road damage detection dashcam India",
    "ytsearch3:bangalore road pothole dashcam footage",
    "ytsearch3:India highway dashcam driving 2024",
]

ydl_opts = {
    "format": "best[height<=480][ext=mp4]/best[height<=480]/best",
    "outtmpl": "tests/sample_images/dashcam_clip.%(ext)s",
    "quiet": True,
    "no_warnings": True,
    "match_filter": yt_dlp.utils.match_filter_func("duration < 300"),  # max 5 min
    "max_downloads": 1,
}

for query in SEARCH_QUERIES:
    print(f"\nSearching: {query}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            # Could be a playlist from search
            if "entries" in info:
                for entry in info["entries"]:
                    if entry:
                        title = entry.get("title", "?")
                        print(f"  Got: {title[:60]}")
                        break
            else:
                print(f"  Got: {info.get('title','?')[:60]}")

        # Verify
        for ext in ["mp4", "webm", "mkv"]:
            f = f"tests/sample_images/dashcam_clip.{ext}"
            if os.path.exists(f) and os.path.getsize(f) > 500_000:
                if f != DEST:
                    os.rename(f, DEST)
                cap = cv2.VideoCapture(DEST)
                ok, frame = cap.read()
                fps = cap.get(cv2.CAP_PROP_FPS)
                nf  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                if ok:
                    print(f"  Video: {w}x{h} @ {fps:.0f}fps, {nf} frames ({nf/max(fps,1):.0f}s), {os.path.getsize(DEST)/1e6:.1f}MB")
                    # Save sample frames at different time points
                    cap2 = cv2.VideoCapture(DEST)
                    for i, pos in enumerate([30, nf//4, nf//2]):
                        cap2.set(cv2.CAP_PROP_POS_FRAMES, min(pos, nf-1))
                        ok2, fr = cap2.read()
                        if ok2:
                            cv2.imwrite(f"tests/sample_images/frame_sample_{i}.jpg", fr)
                    cap2.release()
                    print(f"  Sample frames saved: frame_sample_0/1/2.jpg")
                    sys.exit(0)
        print("  No valid video file found after download")
    except Exception as e:
        print(f"  Error: {str(e)[:100]}")

print("\nAll search attempts failed.")
