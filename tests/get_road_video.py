"""
get_road_video.py
=================
Fetch a real road/dashcam video from reliable open sources.
Tries multiple strategies in order.
"""
import requests, os, subprocess, sys

os.makedirs("tests/sample_images", exist_ok=True)
DEST = "tests/sample_images/dashcam_clip.mp4"
HDR  = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Strategy 1: Wikimedia Commons road video (confirmed public domain MP4s)
WIKIMEDIA = [
    "https://upload.wikimedia.org/wikipedia/commons/transcoded/8/8e/Mumbai_Pune_Expressway.webm/Mumbai_Pune_Expressway.webm.360p.vp9.webm",
    "https://upload.wikimedia.org/wikipedia/commons/9/90/Indian_Traffic_at_the_Main_Road.ogv",
    "https://upload.wikimedia.org/wikipedia/commons/transcoded/9/90/Indian_Traffic_at_the_Main_Road.ogv/Indian_Traffic_at_the_Main_Road.ogv.360p.webm",
    "https://upload.wikimedia.org/wikipedia/commons/transcoded/a/a7/Driving_in_Mumbai.webm/Driving_in_Mumbai.webm.360p.webm",
    "https://upload.wikimedia.org/wikipedia/commons/transcoded/0/09/Road_in_India.ogv/Road_in_India.ogv.360p.webm",
]

# Strategy 2: Internet Archive road footage
ARCHIVE = [
    "https://archive.org/download/IP_Cameras/dashcam_road.mp4",
    "https://ia800200.us.archive.org/8/items/drive&listen_clips/mumbai_drive.mp4",
]

# Strategy 3: Coverr / free video CDNs
COVERR = [
    "https://cdn.coverr.co/videos/coverr-driving-on-a-road-in-the-mountains-6572/1080p.mp4",
    "https://cdn.coverr.co/videos/coverr-aerial-view-of-a-highway-intersection-5990/720p.mp4",
    "https://cdn.coverr.co/videos/coverr-driving-through-city-streets-at-night-1584/720p.mp4",
]

def try_download(url: str, dest: str) -> bool:
    try:
        r = requests.get(url, headers=HDR, timeout=30, stream=True, allow_redirects=True)
        ct = r.headers.get("content-type", "")
        cl = int(r.headers.get("content-length", 0))
        print(f"  HTTP {r.status_code}  ct={ct[:35]}  size={cl/1e6:.1f}MB")
        if r.status_code != 200 or not any(x in ct for x in ["video", "octet", "webm", "ogg"]):
            return False
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                downloaded += len(chunk)
                if cl:
                    print(f"\r  {downloaded/1e6:.1f}/{cl/1e6:.1f} MB", end="", flush=True)
        print()
        if os.path.getsize(dest) > 100_000:
            print(f"  Saved: {dest}  ({os.path.getsize(dest)/1e6:.1f} MB)")
            return True
        os.remove(dest)
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False

# Strategy 4: yt-dlp on a confirmed-working dashcam upload
YT_URLS = [
    "https://www.youtube.com/watch?v=s86-Z-CbaHA",  # Indian road dashcam
    "https://www.youtube.com/watch?v=5LFkA0NEkr0",  # Bangalore roads
    "https://www.youtube.com/watch?v=BHACKCNDMW8",  # Road trip India
    "https://www.youtube.com/watch?v=dkXm2DJLsyo",  # Mumbai driving
    "https://www.youtube.com/watch?v=c0asJgSyxcY",  # Road damage India
    "https://www.youtube.com/watch?v=J---aiyznGQ",  # Keyboard cat (fallback)
]

def try_ytdlp(url: str, dest: str) -> bool:
    try:
        import yt_dlp
        ydl_opts = {
            "format": "bestvideo[height<=480][vcodec^=avc]+bestaudio[acodec^=mp4a]/best[height<=480][ext=mp4]/best[height<=480]/best",
            "outtmpl": dest.replace(".mp4", ".%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Find the actual output file
            for ext in ["mp4", "mkv", "webm"]:
                candidate = dest.replace(".mp4", f".{ext}")
                if os.path.exists(candidate) and os.path.getsize(candidate) > 100_000:
                    if candidate != dest:
                        os.rename(candidate, dest)
                    size = os.path.getsize(dest)
                    print(f"  Downloaded: {info.get('title','?')[:50]}  ({size/1e6:.1f} MB)")
                    return True
        return False
    except Exception as e:
        print(f"  yt-dlp error: {str(e)[:80]}")
        return False

for label, urls, fn in [
    ("Wikimedia", WIKIMEDIA, try_download),
    ("yt-dlp",    YT_URLS,   try_ytdlp),
    ("Coverr",    COVERR,    try_download),
]:
    print(f"\n--- Trying {label} ---")
    for url in urls:
        print(f"URL: {url[:70]}")
        if fn(url, DEST):
            # Quick verify with cv2
            import cv2
            cap = cv2.VideoCapture(DEST)
            ok, f = cap.read()
            cap.release()
            if ok and f is not None:
                cap2 = cv2.VideoCapture(DEST)
                fps  = cap2.get(cv2.CAP_PROP_FPS)
                nf   = int(cap2.get(cv2.CAP_PROP_FRAME_COUNT))
                w    = int(cap2.get(cv2.CAP_PROP_FRAME_WIDTH))
                h    = int(cap2.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap2.release()
                print(f"\nVIDEO OK: {w}x{h}  {fps:.0f}fps  {nf} frames  ({nf/fps:.1f}s)")
                # Save a sample frame
                cap3 = cv2.VideoCapture(DEST)
                cap3.set(cv2.CAP_PROP_POS_FRAMES, min(60, nf//2))
                ok2, frame = cap3.read()
                if ok2:
                    cv2.imwrite("tests/sample_images/input_sample_frame.jpg", frame)
                    print("Sample frame saved: tests/sample_images/input_sample_frame.jpg")
                cap3.release()
                print(f"\nTo run live pipeline:")
                print(f"  python tests/live_dashcam_pipeline.py --source {DEST} --headless --max-frames 300 --save tests/sample_images/dashcam_annotated.mp4")
                sys.exit(0)
            else:
                print("  File not readable by cv2, skipping")
                os.remove(DEST)

print("\nAll sources failed. Using synthetic demo mode instead.")
print("  python tests/live_dashcam_pipeline.py --demo --headless --max-frames 100 --save tests/sample_images/demo_annotated.mp4")
