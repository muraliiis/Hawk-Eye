"""Download a public domain road video for inference testing."""
import requests, os

os.makedirs("tests/sample_images", exist_ok=True)
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

sources = [
    "https://cdn.pixabay.com/video/2016/12/27/6962-197634069_large.mp4",
    "https://videos.pexels.com/video-files/3993644/3993644-uhd_2560_1440_25fps.mp4",
    "https://www.pexels.com/download/video/2278095/",
    "https://cdn.pixabay.com/video/2020/07/31/46076-447087923_large.mp4",
]

for url in sources:
    dest = "tests/sample_images/dashcam_clip.mp4"
    try:
        r = requests.get(url, headers=headers, timeout=25, stream=True, allow_redirects=True)
        ct = r.headers.get("content-type", "")
        print(f"HTTP {r.status_code}  content-type={ct[:40]}  {url[:60]}")
        if r.status_code == 200 and ("video" in ct or "octet" in ct):
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
                    downloaded += len(chunk)
            size = os.path.getsize(dest)
            print(f"Downloaded: {dest}  ({size/1e6:.1f} MB)")
            break
        else:
            print(f"  Skipping — not a video response")
    except Exception as e:
        print(f"Failed: {e}")
