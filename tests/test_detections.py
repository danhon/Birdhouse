"""Tests for detection filtering, deduplication, and sorting."""

from zoneinfo import ZoneInfo

import pytest

from birdhouse.app import Species, _format_time, unique_species_from_detections

TZ = ZoneInfo("America/Los_Angeles")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _det(sci, common, ts, confidence=0.8):
    return {
        "scientificName": sci,
        "commonName": common,
        "timestamp": ts,
        "confidence": confidence,
    }


CROW   = _det("Corvus brachyrhynchos", "American Crow",    "2026-05-12T08:00:00-07:00")
FINCH  = _det("Haemorhous mexicanus",  "House Finch",       "2026-05-12T07:00:00-07:00")
FINCH2 = _det("Haemorhous mexicanus",  "House Finch",       "2026-05-12T09:00:00-07:00")  # duplicate, later
WARBL  = _det("Setophaga townsendi",   "Townsend's Warbler","2026-05-12T06:00:00-07:00")
LOW    = _det("Troglodytes aedon",     "House Wren",        "2026-05-12T05:00:00-07:00", confidence=0.3)


# ---------------------------------------------------------------------------
# unique_species_from_detections
# ---------------------------------------------------------------------------

class TestUniqueSpecies:
    def test_returns_one_entry_per_species(self):
        result = unique_species_from_detections([FINCH, FINCH2, CROW], 0.6, TZ)
        sci_names = [s.scientific_name for s in result]
        assert sci_names.count("Haemorhous mexicanus") == 1

    def test_sorted_by_first_detection(self):
        result = unique_species_from_detections([CROW, FINCH, WARBL], 0.6, TZ)
        assert [s.scientific_name for s in result] == [
            "Setophaga townsendi",    # 06:00
            "Haemorhous mexicanus",   # 07:00
            "Corvus brachyrhynchos",  # 08:00
        ]

    def test_keeps_earliest_detection_for_duplicates(self):
        result = unique_species_from_detections([FINCH2, FINCH], 0.6, TZ)
        sp = result[0]
        # 07:00 is earlier than 09:00
        assert sp.first_seen == "7:00 am"

    def test_filters_low_confidence(self):
        result = unique_species_from_detections([LOW, FINCH], 0.6, TZ)
        sci_names = [s.scientific_name for s in result]
        assert "Troglodytes aedon" not in sci_names
        assert "Haemorhous mexicanus" in sci_names

    def test_confidence_exactly_at_threshold_is_included(self):
        at_threshold = _det("Troglodytes aedon", "House Wren", "2026-05-12T05:00:00-07:00", confidence=0.6)
        result = unique_species_from_detections([at_threshold], 0.6, TZ)
        assert len(result) == 1

    def test_empty_detections_returns_empty(self):
        result = unique_species_from_detections([], 0.6, TZ)
        assert result == []

    def test_skips_detections_with_no_scientific_name(self):
        bad = _det("", "Unknown", "2026-05-12T08:00:00-07:00")
        result = unique_species_from_detections([bad, FINCH], 0.6, TZ)
        assert len(result) == 1
        assert result[0].scientific_name == "Haemorhous mexicanus"

    def test_result_is_species_dataclass(self):
        result = unique_species_from_detections([FINCH], 0.6, TZ)
        assert len(result) == 1
        sp = result[0]
        assert isinstance(sp, Species)
        assert sp.common_name == "House Finch"
        assert sp.scientific_name == "Haemorhous mexicanus"
        assert sp.image_path is None

    def test_missing_confidence_field_is_excluded(self):
        no_conf = {"scientificName": "Corvus brachyrhynchos", "commonName": "American Crow",
                   "timestamp": "2026-05-12T08:00:00-07:00"}
        result = unique_species_from_detections([no_conf], 0.6, TZ)
        assert result == []


# ---------------------------------------------------------------------------
# _format_time
# ---------------------------------------------------------------------------

class TestFormatTime:
    def test_formats_am(self):
        assert _format_time("2026-05-12T07:24:00-07:00", TZ) == "7:24 am"

    def test_formats_pm(self):
        assert _format_time("2026-05-12T17:05:00-07:00", TZ) == "5:05 pm"

    def test_noon_is_pm(self):
        assert _format_time("2026-05-12T12:00:00-07:00", TZ) == "12:00 pm"

    def test_midnight_is_am(self):
        assert _format_time("2026-05-12T00:00:00-07:00", TZ) == "12:00 am"

    def test_empty_string_returns_empty(self):
        assert _format_time("", TZ) == ""

    def test_invalid_returns_original(self):
        assert _format_time("not-a-date", TZ) == "not-a-date"
