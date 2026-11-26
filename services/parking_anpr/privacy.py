from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List

import cv2
import numpy as np

from .config import settings

logger = logging.getLogger(__name__)

# Fixed salt fallback ensures consistent anonymisation across service restarts.
# In production, override via PARKING_PRIVACY_SALT environment variable.
_SALT = os.getenv("PARKING_PRIVACY_SALT", "parking_anpr_v1_salt")

# Pixelation block size (px) used when masking plates in frames.
_PIXELATE_BLOCK = 10


class PrivacyManager:
    """
    Handles all privacy-sensitive operations for the parking / ANPR pipeline:

    * Plate-level anonymisation for database storage (hashed).
    * Display-level anonymisation for video frames (pixelation).
    * Retention-policy enforcement.
    """

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    def should_retain(
        self,
        plate_text: str,
        timestamp: datetime,
        is_flagged: bool = False,
    ) -> bool:
        """
        Determine whether a plate observation should still be retained.

        Args:
            plate_text: The raw (un-anonymised) plate string — used only as a
                        label; the value itself is not stored by this method.
            timestamp: The UTC datetime when the plate was first observed.
            is_flagged: If *True*, the extended flagged-retention window
                        (``settings.flagged_retention_days``) applies.

        Returns:
            ``True`` if the record is within its retention window and should
            be kept; ``False`` if it has expired and may be deleted.
        """
        now = datetime.now(timezone.utc)

        # Normalise naïve timestamps to UTC for safe arithmetic.
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        if is_flagged:
            cutoff = now - timedelta(days=settings.flagged_retention_days)
        else:
            cutoff = now - timedelta(hours=settings.plate_retention_hours)

        retain = timestamp >= cutoff
        logger.debug(
            "PrivacyManager.should_retain: plate=%s flagged=%s retain=%s",
            plate_text[:4] + "***",
            is_flagged,
            retain,
        )
        return retain

    # ------------------------------------------------------------------
    # Frame-level masking
    # ------------------------------------------------------------------

    def mask_plate_in_frame(
        self,
        frame: np.ndarray,
        plate_bbox: List[float],
    ) -> np.ndarray:
        """
        Pixelate the plate region in *frame* in-place and return the result.

        The region is downsampled to a small size and then upscaled back to its
        original dimensions using nearest-neighbour interpolation, producing a
        mosaic / pixelation effect without hard-coding a blur radius.

        Args:
            frame: BGR image as a NumPy array (H, W, 3).  Modified in-place.
            plate_bbox: ``[x1, y1, x2, y2]`` bounding box in absolute pixel
                        coordinates.

        Returns:
            The modified frame (same object as the input).
        """
        x1, y1, x2, y2 = (int(v) for v in plate_bbox)
        x1, y1 = max(x1, 0), max(y1, 0)
        x2, y2 = min(x2, frame.shape[1]), min(y2, frame.shape[0])

        if x2 <= x1 or y2 <= y1:
            return frame

        roi = frame[y1:y2, x1:x2]
        roi_h, roi_w = roi.shape[:2]

        # Down-sample to block-grid, then up-sample back
        small_w = max(roi_w // _PIXELATE_BLOCK, 1)
        small_h = max(roi_h // _PIXELATE_BLOCK, 1)
        small = cv2.resize(roi, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
        pixelated = cv2.resize(small, (roi_w, roi_h), interpolation=cv2.INTER_NEAREST)

        frame[y1:y2, x1:x2] = pixelated
        return frame

    # ------------------------------------------------------------------
    # Storage anonymisation
    # ------------------------------------------------------------------

    def anonymize_for_storage(self, plate_text: str) -> str:
        """
        Return a 16-character hex digest suitable for pseudonymous storage.

        The digest is derived from ``SHA-256(salt + plate_text)`` and is
        deterministic — the same plate always produces the same token, allowing
        re-identification for law-enforcement purposes while preventing casual
        linkage.

        Args:
            plate_text: The raw plate string (e.g. ``"MH12AB1234"``).

        Returns:
            A 16-character lowercase hex string.
        """
        payload = (_SALT + plate_text).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        return digest[:16]
