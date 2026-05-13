"""Tests for _format_time and the CommonNameCache."""

import pytest
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock

from birdhouse.app import CommonNameCache, _format_time

TZ = ZoneInfo("America/Los_Angeles")


def _ts(hour: int, minute: int = 0, date: str = "2026-05-12") -> int:
    """Return a Unix timestamp for the given local date/time."""
    from datetime import datetime
    y, m, d = (int(x) for x in date.split("-"))
    dt = datetime(y, m, d, hour, minute, 0, tzinfo=TZ)
    return int(dt.timestamp())


TS_7AM  = _ts(7)
TS_5PM  = _ts(17)
TS_NOON = _ts(12)
TS_MID  = _ts(0)


class TestFormatTime:
    def test_formats_am(self):
        result = _format_time(TS_7AM, TZ)
        assert result == "7:00 am"

    def test_formats_pm(self):
        result = _format_time(TS_5PM, TZ)
        assert result == "5:00 pm"

    def test_noon_is_pm(self):
        result = _format_time(TS_NOON, TZ)
        assert result == "12:00 pm"

    def test_midnight_is_am(self):
        result = _format_time(TS_MID, TZ)
        assert result == "12:00 am"

    def test_invalid_returns_empty(self):
        assert _format_time(-99999999999, TZ) == ""


class TestCommonNameCache:
    def _make_cache(self, entries: dict) -> CommonNameCache:
        cache = CommonNameCache()
        cache._cache.update(entries)
        return cache

    def test_returns_common_name_when_cached(self):
        cache = self._make_cache({"Corvus brachyrhynchos": "American Crow"})
        assert cache.get("Corvus brachyrhynchos") == "American Crow"

    def test_falls_back_to_scientific_name_when_missing(self):
        cache = CommonNameCache()
        assert cache.get("Corvus brachyrhynchos") == "Corvus brachyrhynchos"

    def test_missing_returns_uncached_names(self):
        cache = self._make_cache({"Corvus brachyrhynchos": "American Crow"})
        missing = cache.missing(["Corvus brachyrhynchos", "Haemorhous mexicanus"])
        assert missing == ["Haemorhous mexicanus"]

    def test_missing_returns_empty_when_all_cached(self):
        cache = self._make_cache({
            "Corvus brachyrhynchos": "American Crow",
            "Haemorhous mexicanus": "House Finch",
        })
        assert cache.missing(["Corvus brachyrhynchos", "Haemorhous mexicanus"]) == []

    def test_seed_populates_cache_from_api_response(self):
        cache = CommonNameCache()
        session = MagicMock()
        session.get.return_value.json.return_value = {
            "data": [
                {"scientificName": "Corvus brachyrhynchos", "commonName": "American Crow"},
                {"scientificName": "Haemorhous mexicanus", "commonName": "House Finch"},
            ]
        }
        session.get.return_value.raise_for_status = MagicMock()
        cache.seed("http://localhost:8888", session)
        assert cache.get("Corvus brachyrhynchos") == "American Crow"
        assert cache.get("Haemorhous mexicanus") == "House Finch"

    def test_seed_handles_api_failure_gracefully(self):
        cache = CommonNameCache()
        session = MagicMock()
        session.get.side_effect = Exception("network error")
        cache.seed("http://localhost:8888", session)  # should not raise
        assert cache.get("Corvus brachyrhynchos") == "Corvus brachyrhynchos"
