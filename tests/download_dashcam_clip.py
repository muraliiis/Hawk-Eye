"""
download_dashcam_clip.py
========================
Download a short road/dashcam clip from a reliable public source for inference testing.
Uses yt-dlp to grab the first available road-damage video.
"""
import yt_dlp
import os

os.makedirs("tests/sample_images", exist_ok=True)

# Road damage / dashcam footage — trying multiple sources
CANDIDATES = [
    "https://www.youtube.com/watch?v=jMOtGOXRZek",   # Indian dashcam
    "https://www.youtube.com/watch?v=MejbOFk7H6c",   # City driving India
    "https://www.youtube.com/watch?v=V4f_1_r80RY",   # Road detection demo
    "https://www.youtube.com/watch?v=e_5GADFCfnY",   # Pothole compilation
    "https://www.youtube.com/watch?v=M0FMCxIRBwA",   # Mumbai traffic
    "https://www.youtube.com/watch?v=aqz-KE-bpKQ",   # Fallback: Big Buck Bunny (connectivity)
]

ydl_opts = {
    "format": "best[height<=480][filesize<50M]/best[height<=480]/best[filesize<80M]",
    "outtmpl": "tests/sample_images/dashcam_clip.%(ext)s",
    "quiet": False,
    "no_warnings": True,
    "max_filesize": 80 * 1024 * 1024,  # 80 MB max
}

for url in CANDIDATES:
    print(f"\nTrying: {url}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            ext = info.get("ext", "mp4")
            out = f"tests/sample_images/dashcam_clip.{ext}"
            if os.path.exists(out):
                size_mb = os.path.getsize(out) / 1e6
                print(f"\nDownloaded: {out}  ({size_mb:.1f} MB)")
                print(f"Title: {info.get('title', '?')}")
                print(f"Duration: {info.get('duration', 0)}s")
                print(f"\nRun pipeline:")
                print(f'  python tests/live_dashcam_pipeline.py --source "{out}" --headless --max-frames 300 --save tests/sample_images/dashcam_annotated.mp4')
                break
    except Exception as e:
        print(f"  Failed: {str(e)[:100]}")
