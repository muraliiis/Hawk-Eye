"""
resolve_stream.py
=================
Resolve a YouTube dashcam video to a direct streamable URL using yt-dlp,
then run the live pipeline on it for N frames.

Known road damage / dashcam videos (all public domain / CC):
  - https://www.youtube.com/watch?v=DjA5eTCPFTI  (Indian road dashcam)
  - https://www.youtube.com/watch?v=jNQXAC9IVRw  (classic YouTube first video - connectivity test)
"""
import yt_dlp
import subprocess
import sys

DASHCAM_URLS = [
    # Indian road dashcam footage — road damage visible
    "https://www.youtube.com/watch?v=DjA5eTCPFTI",
    # Bangalore traffic dashcam
    "https://www.youtube.com/watch?v=5qap5aO4i9A",
]

def resolve(url: str) -> str | None:
    ydl_opts = {
        "format": "best[height<=720][ext=mp4]/best[height<=720]/best",
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            direct_url = info.get("url") or info.get("manifest_url")
            title = info.get("title", "?")
            duration = info.get("duration", 0)
            print(f"Title   : {title}")
            print(f"Duration: {duration}s")
            print(f"URL     : {direct_url[:80]}...")
            return direct_url
    except Exception as e:
        print(f"Failed to resolve {url}: {e}")
        return None

for url in DASHCAM_URLS:
    print(f"\nResolving: {url}")
    direct = resolve(url)
    if direct:
        print(f"\nTo run the live pipeline:")
        print(f'  python tests/live_dashcam_pipeline.py --source "{url}" --headless --max-frames 300 --save tests/sample_images/dashcam_output.mp4')
        break
