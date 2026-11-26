#!/usr/bin/env python3
"""
download_weights.py
===================
Downloads the model weights required by the parking / ANPR pipeline and saves
them to ``services/parking_anpr/models/``.

Models downloaded
-----------------
* ``yolov8n.pt``  — from the Ultralytics GitHub release assets.
* ``best.pt``     — Koushim/yolov8-license-plate-detection (Hugging Face).

Usage
-----
    python services/parking_anpr/models/download_weights.py
"""

from __future__ import annotations

import hashlib
import os
import sys

import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Resolve models dir relative to this script regardless of cwd.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = _SCRIPT_DIR  # This script lives inside models/


def _dest(filename: str) -> str:
    return os.path.join(MODELS_DIR, filename)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_file(path: str) -> str:
    """Return the hex SHA-256 digest of the file at *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_with_progress(url: str, dest_path: str) -> None:
    """
    Stream *url* to *dest_path*, showing a tqdm progress bar.
    Resumes partial downloads if the file already exists.
    """
    # Check whether the file is already fully downloaded.
    if os.path.exists(dest_path):
        print(f"  ✓ {os.path.basename(dest_path)} already exists, skipping download.")
        return

    print(f"  ↓ Downloading {url}")
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    with (
        open(dest_path, "wb") as fh,
        tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=os.path.basename(dest_path),
            leave=True,
        ) as bar,
    ):
        for chunk in response.iter_content(chunk_size=1 << 16):
            fh.write(chunk)
            bar.update(len(chunk))

    print(f"  ✓ Saved to {dest_path}")


# ---------------------------------------------------------------------------
# Download targets
# ---------------------------------------------------------------------------


def download_yolov8n() -> None:
    url = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt"
    dest = _dest("yolov8n.pt")
    print("\n[1/2] YOLOv8n vehicle detector")
    download_with_progress(url, dest)
    checksum = sha256_file(dest)
    print(f"      SHA-256: {checksum}")


def download_plate_model() -> None:
    print("\n[2/2] YOLOv8 license-plate detector (Koushim/yolov8-license-plate-detection)")
    try:
        from huggingface_hub import hf_hub_download  # type: ignore
    except ImportError:
        print("  ✗ huggingface_hub is not installed.  Run:  pip install huggingface-hub")
        sys.exit(1)

    dest = _dest("best.pt")
    if os.path.exists(dest):
        print(f"  ✓ {os.path.basename(dest)} already exists, skipping download.")
    else:
        print("  ↓ Fetching from Hugging Face Hub …")
        cached_path = hf_hub_download(
            repo_id="Koushim/yolov8-license-plate-detection",
            filename="best.pt",
        )
        # hf_hub_download returns a path in the HF cache; copy to models dir.
        import shutil

        shutil.copy2(cached_path, dest)
        print(f"  ✓ Saved to {dest}")

    checksum = sha256_file(dest)
    print(f"      SHA-256: {checksum}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)
    print(f"Models directory: {MODELS_DIR}")

    download_yolov8n()
    download_plate_model()

    print("\n✅  All weights downloaded successfully.")


if __name__ == "__main__":
    main()
