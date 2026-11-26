"""
find_stream.py
==============
Search for available road dashcam videos and resolve the best one.
"""
import yt_dlp

# Well-known, stable road/dashcam/traffic clips from YouTube
CANDIDATES = [
    ("Big Buck Bunny (connectivity test)",     "https://www.youtube.com/watch?v=aqz-KE-bpKQ"),
    ("Indian road dashcam compilation",         "https://www.youtube.com/watch?v=jMOtGOXRZek"),
    ("Bangalore road pothole compilation",      "https://www.youtube.com/watch?v=e_5GADFCfnY"),
    ("Mumbai traffic dashcam",                  "https://www.youtube.com/watch?v=M0FMCxIRBwA"),
    ("Road damage detection demo",              "https://www.youtube.com/watch?v=V4f_1_r80RY"),
    ("Driving through Indian city",             "https://www.youtube.com/watch?v=MejbOFk7H6c"),
]

ydl_opts = {
    "format": "best[height<=480][ext=mp4]/best[height<=480]/bestvideo[height<=480]+bestaudio/best",
    "quiet": True,
    "no_warnings": True,
}

for title, url in CANDIDATES:
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            direct = info.get("url") or info.get("manifest_url", "")
            dur = info.get("duration", 0)
            vtitle = info.get("title", "?")
            print(f"OK  [{dur:4d}s]  {vtitle[:60]}")
            print(f"     URL: {url}")
            print(f"     CMD: python tests/live_dashcam_pipeline.py --source \"{url}\" --headless --max-frames 500 --save tests/sample_images/dashcam_result.mp4")
            print()
            break  # Use the first working one
    except Exception as e:
        print(f"SKIP {title}: {str(e)[:80]}")
