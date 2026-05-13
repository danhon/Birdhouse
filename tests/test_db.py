"""Tests for BirdNET-Go SQLite queries."""

import sqlite3
import pytest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from birdhouse.app import query_today_from_db, _day_bounds

TZ = ZoneInfo("America/Los_Angeles")


# ---------------------------------------------------------------------------
# Fixtures — in-memory SQLite DB matching BirdNET-Go's schema
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path) -> Path:
    path = tmp_path / "birdnet.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE labels (
            id INTEGER PRIMARY KEY,
            scientific_name TEXT NOT NULL,
            model_id INTEGER,
            label_type_id INTEGER,
            taxonomic_class_id INTEGER,
            created_at TEXT
        );
        CREATE TABLE detections (
            id INTEGER PRIMARY KEY,
            model_id INTEGER,
            label_id INTEGER,
            source_id INTEGER,
            detected_at INTEGER,
            confidence REAL,
            clip_name TEXT
        );
        CREATE TABLE image_caches (
            id INTEGER PRIMARY KEY,
            provider_name TEXT,
            label_id INTEGER,
            url TEXT,
            cached_at TEXT
        );

        INSERT INTO labels VALUES (1, 'Corvus brachyrhynchos', 1, 1, 1, '');
        INSERT INTO labels VALUES (2, 'Haemorhous mexicanus',  1, 1, 1, '');
        INSERT INTO labels VALUES (3, 'Setophaga townsendi',   1, 1, 1, '');

        INSERT INTO image_caches VALUES (1, 'wikimedia', 1, 'https://example.com/crow.jpg', '');
        INSERT INTO image_caches VALUES (2, 'avicommons', 2, 'https://avicommons.org/finch.jpg', '');
        INSERT INTO image_caches VALUES (3, 'wikimedia', 2, 'https://example.com/finch-wiki.jpg', '');
    """)
    conn.commit()
    conn.close()
    return path


def _insert_detection(db_path: Path, label_id: int, detected_at: int, confidence: float = 0.8):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO detections (label_id, detected_at, confidence) VALUES (?, ?, ?)",
        (label_id, detected_at, confidence),
    )
    conn.commit()
    conn.close()


def _today_ts(hour: int, minute: int = 0) -> int:
    """Return a Unix timestamp for today at the given local time."""
    now = datetime.now(TZ)
    dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return int(dt.timestamp())


def _yesterday_ts(hour: int = 12) -> int:
    from datetime import timedelta
    now = datetime.now(TZ)
    dt = (now - timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# query_today_from_db
# ---------------------------------------------------------------------------

class TestQueryTodayFromDb:
    def test_returns_species_detected_today(self, db_path):
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(8))
        rows = query_today_from_db(db_path, TZ)
        assert len(rows) == 1
        assert rows[0][0] == "Corvus brachyrhynchos"

    def test_excludes_yesterday(self, db_path):
        _insert_detection(db_path, label_id=1, detected_at=_yesterday_ts())
        rows = query_today_from_db(db_path, TZ)
        assert rows == []

    def test_counts_multiple_detections(self, db_path):
        for hour in [8, 9, 10]:
            _insert_detection(db_path, label_id=1, detected_at=_today_ts(hour))
        rows = query_today_from_db(db_path, TZ)
        assert rows[0][3] == 3

    def test_sorted_by_first_detection(self, db_path):
        _insert_detection(db_path, label_id=2, detected_at=_today_ts(9))
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(7))
        _insert_detection(db_path, label_id=3, detected_at=_today_ts(11))
        rows = query_today_from_db(db_path, TZ)
        names = [r[0] for r in rows]
        assert names == ["Corvus brachyrhynchos", "Haemorhous mexicanus", "Setophaga townsendi"]

    def test_first_seen_is_earliest_timestamp(self, db_path):
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(10))
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(8))
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(12))
        rows = query_today_from_db(db_path, TZ)
        assert rows[0][1] == _today_ts(8)

    def test_last_seen_is_latest_timestamp(self, db_path):
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(10))
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(8))
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(12))
        rows = query_today_from_db(db_path, TZ)
        assert rows[0][2] == _today_ts(12)

    def test_last_seen_equals_first_seen_for_single_detection(self, db_path):
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(9))
        rows = query_today_from_db(db_path, TZ)
        assert rows[0][1] == rows[0][2]

    def test_excludes_below_min_confidence(self, db_path):
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(8), confidence=0.4)
        rows = query_today_from_db(db_path, TZ, min_confidence=0.6)
        assert rows == []

    def test_includes_at_min_confidence(self, db_path):
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(8), confidence=0.6)
        rows = query_today_from_db(db_path, TZ, min_confidence=0.6)
        assert len(rows) == 1

    def test_zero_confidence_includes_all(self, db_path):
        _insert_detection(db_path, label_id=1, detected_at=_today_ts(8), confidence=0.1)
        _insert_detection(db_path, label_id=2, detected_at=_today_ts(9), confidence=0.9)
        rows = query_today_from_db(db_path, TZ, min_confidence=0.0)
        assert len(rows) == 2

    def test_returns_empty_on_missing_db(self, tmp_path):
        rows = query_today_from_db(tmp_path / "nonexistent.db", TZ)
        assert rows == []

