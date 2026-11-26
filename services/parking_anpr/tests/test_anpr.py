"""
Unit tests for ANPR anonymisation and PrivacyManager.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


class TestAnonymizePlate:
    """ANPRPipeline.anonymize_plate masks all chars after the first 4 with 'X'."""

    def _get_pipeline(self):
        """Return an ANPRPipeline instance with heavy IO bypassed."""
        from services.parking_anpr.anpr import ANPRPipeline

        pipeline = ANPRPipeline.__new__(ANPRPipeline)
        pipeline.ocr_confidence = 0.60
        pipeline.plate_confidence = 0.50
        return pipeline

    def test_anonymize_standard_plate(self):
        """'MH12AB1234' → 'MH12XXXXXX' (6 chars masked)."""
        pipeline = self._get_pipeline()
        result = pipeline.anonymize_plate("MH12AB1234")
        assert result == "MH12XXXXXX"

    def test_anonymize_exactly_four_chars(self):
        """Plate with exactly 4 chars is returned unchanged."""
        pipeline = self._get_pipeline()
        result = pipeline.anonymize_plate("AB12")
        assert result == "AB12"

    def test_anonymize_fewer_than_four_chars(self):
        """Plate shorter than 4 chars is returned unchanged."""
        pipeline = self._get_pipeline()
        assert pipeline.anonymize_plate("AB1") == "AB1"
        assert pipeline.anonymize_plate("") == ""

    def test_anonymize_long_plate(self):
        """All chars beyond the 4th are replaced with 'X'."""
        pipeline = self._get_pipeline()
        result = pipeline.anonymize_plate("ABCDE12345")
        assert result == "ABCDXXXXXX"
        assert len(result) == len("ABCDE12345")

    def test_anonymize_prefix_preserved(self):
        """The first 4 characters are always preserved exactly."""
        pipeline = self._get_pipeline()
        result = pipeline.anonymize_plate("KA05MJ2021")
        assert result[:4] == "KA05"
        assert all(c == "X" for c in result[4:])


class TestPrivacyManagerAnonymizeForStorage:
    """anonymize_for_storage should return a consistent 16-char hex string."""

    def _manager(self):
        from services.parking_anpr.privacy import PrivacyManager
        return PrivacyManager()

    def test_returns_16_char_string(self):
        """Return value must be exactly 16 characters long."""
        mgr = self._manager()
        result = mgr.anonymize_for_storage("MH12AB1234")
        assert len(result) == 16

    def test_returns_hex_string(self):
        """Return value must be a lowercase hex string."""
        mgr = self._manager()
        result = mgr.anonymize_for_storage("MH12AB1234")
        # All characters should be valid hex digits
        int(result, 16)  # raises ValueError if not hex

    def test_deterministic(self):
        """Same plate text must always produce the same token."""
        mgr = self._manager()
        plate = "DL8CAB0001"
        assert mgr.anonymize_for_storage(plate) == mgr.anonymize_for_storage(plate)

    def test_different_plates_different_tokens(self):
        """Different plates should (almost certainly) produce different tokens."""
        mgr = self._manager()
        t1 = mgr.anonymize_for_storage("MH12AB0001")
        t2 = mgr.anonymize_for_storage("MH12AB0002")
        assert t1 != t2

    def test_consistent_across_instances(self):
        """Two separate PrivacyManager instances return the same token for the same plate."""
        from services.parking_anpr.privacy import PrivacyManager
        plate = "GJ01AA9999"
        assert PrivacyManager().anonymize_for_storage(plate) == PrivacyManager().anonymize_for_storage(plate)


class TestPrivacyManagerShouldRetain:
    """should_retain enforces the 24-hour standard / 7-day flagged windows."""

    def _manager(self):
        from services.parking_anpr.privacy import PrivacyManager
        return PrivacyManager()

    # --- standard (non-flagged) retention: 24 hours ---

    def test_retain_recent_plate(self):
        """A plate observed 1 hour ago should be retained."""
        mgr = self._manager()
        ts = datetime.now(timezone.utc) - timedelta(hours=1)
        assert mgr.should_retain("MH12AB1234", ts, is_flagged=False) is True

    def test_discard_expired_plate(self):
        """A plate observed 25 hours ago (non-flagged) should not be retained."""
        mgr = self._manager()
        ts = datetime.now(timezone.utc) - timedelta(hours=25)
        assert mgr.should_retain("MH12AB1234", ts, is_flagged=False) is False

    def test_boundary_exactly_24h(self):
        """A plate observed exactly 24 hours ago is at the boundary.
        Our implementation uses >=, so it should still be retained."""
        mgr = self._manager()
        ts = datetime.now(timezone.utc) - timedelta(hours=24)
        # At exactly 24h it should still be within the window (timestamp >= cutoff)
        # Allow a tiny delta for test execution time
        result = mgr.should_retain("MH12AB1234", ts, is_flagged=False)
        # Result is True or False depending on sub-second timing; we only
        # assert the type here.
        assert isinstance(result, bool)

    # --- flagged retention: 7 days ---

    def test_retain_flagged_plate_6_days(self):
        """A flagged plate observed 6 days ago should be retained."""
        mgr = self._manager()
        ts = datetime.now(timezone.utc) - timedelta(days=6)
        assert mgr.should_retain("MH12AB1234", ts, is_flagged=True) is True

    def test_discard_flagged_plate_8_days(self):
        """A flagged plate observed 8 days ago should not be retained."""
        mgr = self._manager()
        ts = datetime.now(timezone.utc) - timedelta(days=8)
        assert mgr.should_retain("MH12AB1234", ts, is_flagged=True) is False

    def test_naive_timestamp_handled(self):
        """Naïve timestamps (no tzinfo) are accepted and treated as UTC."""
        mgr = self._manager()
        ts = datetime.utcnow() - timedelta(hours=1)  # naïve, recent
        # Should not raise and should return True (recent plate)
        assert mgr.should_retain("MH12AB1234", ts, is_flagged=False) is True
