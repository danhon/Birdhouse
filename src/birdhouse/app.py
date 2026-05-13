"""
Birdhouse — full-bleed bird species carousel from BirdNET-Go detections.

Queries the BirdNET-Go SQLite database directly for accurate per-day counts
and first-detection times. Uses BirdNET-Go's own image_caches table for
species photos. Fetches common names from the BirdNET-Go REST API.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from flask import Flask, render_template

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    birdnet_base_url: str
    birdnet_db_path: Path
    port: int
    min_confidence: float
    timezone: ZoneInfo
    poll_interval: int
    slide_duration: int

    @classmethod
    def from_env(cls) -> "Config":
        import os
        return cls(
            birdnet_base_url=os.environ.get("BIRDNET_BASE_URL", "http://192.168.1.100:8888").rstrip("/"),
            birdnet_db_path=Path(os.environ.get("BIRDNET_DB_PATH", "/home/danhon/birdnet-go-app/data/birdnet.db")),
            port=int(os.environ.get("PORT", "8090")),
            min_confidence=float(os.environ.get("MIN_CONFIDENCE", "0.6")),
            timezone=ZoneInfo(os.environ.get("TZ", "America/Los_Angeles")),
            poll_interval=int(os.environ.get("POLL_INTERVAL", "60")),
            slide_duration=int(os.environ.get("SLIDE_DURATION", "8")),
        )


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Species:
    common_name: str
    scientific_name: str
    first_seen: str        # "5:24 pm" local time
    detection_count: int = 0
    image_url: Optional[str] = None


# ---------------------------------------------------------------------------
# BirdNET-Go database
# ---------------------------------------------------------------------------

def _day_bounds(tz: ZoneInfo) -> tuple[int, int]:
    """Return (start_ts, end_ts) Unix timestamps for today in the given timezone."""
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return int(start.timestamp()), int(end.timestamp())


def query_today_from_db(
    db_path: Path,
    tz: ZoneInfo,
    min_confidence: float,
) -> list[tuple[str, int, int]]:
    """
    Query the BirdNET-Go SQLite database for today's species.

    Returns a list of (scientific_name, first_seen_unix_ts, detection_count)
    sorted by first detection time ascending.
    """
    ts_start, ts_end = _day_bounds(tz)
    try:
        # Open read-only with immutable=1 so SQLite skips all locking —
        # safe because BirdNET-Go owns the DB and we only read.
        # This also works when the DB is on a network filesystem (SMB/NFS)
        # where WAL-mode locking is unsupported.
        uri = f"file:{db_path}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT l.scientific_name,
                   MIN(d.detected_at) AS first_seen,
                   COUNT(*)           AS n
            FROM detections d
            JOIN labels l ON l.id = d.label_id
            WHERE d.detected_at BETWEEN ? AND ?
              AND d.confidence >= ?
            GROUP BY d.label_id
            ORDER BY first_seen ASC
            """,
            (ts_start, ts_end, min_confidence),
        ).fetchall()
        conn.close()
        return [(r["scientific_name"], r["first_seen"], r["n"]) for r in rows]
    except Exception as exc:
        log.error("DB query failed: %s", exc)
        return []


def get_image_url_from_db(db_path: Path, scientific_name: str) -> Optional[str]:
    """
    Return a cached image URL from BirdNET-Go's image_caches table, or None.
    Prefers avicommons URLs (higher resolution) over Wikimedia when both exist.
    """
    try:
        uri = f"file:{db_path}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ic.url
            FROM image_caches ic
            JOIN labels l ON l.id = ic.label_id
            WHERE l.scientific_name = ?
              AND ic.url IS NOT NULL
            """,
            (scientific_name,),
        ).fetchall()
        conn.close()
        if not rows:
            return None
        urls = [r["url"] for r in rows]
        # Prefer avicommons (typically larger/higher quality)
        for url in urls:
            if "avicommons" in url:
                return url
        return urls[0]
    except Exception as exc:
        log.warning("Image URL lookup failed for %s: %s", scientific_name, exc)
        return None


# ---------------------------------------------------------------------------
# Common name cache
# ---------------------------------------------------------------------------

class CommonNameCache:
    """
    Lazy in-memory cache mapping scientific_name → common_name.
    Populated from the BirdNET-Go REST API (which includes commonName in
    detection records). Falls back to the scientific name if unknown.
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, scientific_name: str) -> str:
        with self._lock:
            return self._cache.get(scientific_name, scientific_name)

    def seed(self, base_url: str, session: requests.Session) -> None:
        """Fetch recent detections from the API to populate the name cache."""
        try:
            resp = session.get(
                f"{base_url}/api/v2/detections",
                params={"limit": 200},
                timeout=10,
            )
            resp.raise_for_status()
            records = resp.json().get("data") or []
            with self._lock:
                for r in records:
                    sci = (r.get("scientificName") or "").strip()
                    common = (r.get("commonName") or "").strip()
                    if sci and common:
                        self._cache[sci] = common
            log.info("Common name cache seeded with %d entries", len(self._cache))
        except Exception as exc:
            log.warning("Common name cache seed failed: %s", exc)

    def missing(self, scientific_names: list[str]) -> list[str]:
        with self._lock:
            return [s for s in scientific_names if s not in self._cache]


_name_cache = CommonNameCache()


# ---------------------------------------------------------------------------
# Time formatting
# ---------------------------------------------------------------------------

def _format_time(unix_ts: int, tz: ZoneInfo) -> str:
    """Convert a Unix timestamp to a friendly local time string, e.g. '7:24 am'."""
    try:
        dt = datetime.fromtimestamp(unix_ts, tz=tz)
        hour = dt.hour % 12 or 12
        ampm = "am" if dt.hour < 12 else "pm"
        return f"{hour}:{dt.minute:02d} {ampm}"
    except (OSError, OverflowError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# Data store (shared between background thread and Flask)
# ---------------------------------------------------------------------------

@dataclass
class DataStore:
    species: list[Species] = field(default_factory=list)
    date_label: str = ""
    last_updated: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, species: list[Species], date_label: str, last_updated: str) -> None:
        with self._lock:
            self.species = species
            self.date_label = date_label
            self.last_updated = last_updated

    def snapshot(self) -> tuple[list[Species], str, str]:
        with self._lock:
            return list(self.species), self.date_label, self.last_updated


_store = DataStore()


# ---------------------------------------------------------------------------
# Background poller
# ---------------------------------------------------------------------------

def _date_label(tz: ZoneInfo) -> str:
    return datetime.now(tz).strftime("%A %-d %B %Y")


def _refresh(config: Config, http: requests.Session) -> None:
    """Fetch today's data from the DB and update the store."""
    log.info("Refreshing from DB: %s", config.birdnet_db_path)

    rows = query_today_from_db(config.birdnet_db_path, config.timezone, config.min_confidence)
    log.info("DB returned %d unique species", len(rows))

    # Top up the common name cache for any species we haven't seen before
    unknown = _name_cache.missing([sci for sci, _, _ in rows])
    if unknown:
        log.info("Seeding common name cache (missing: %s)", unknown)
        _name_cache.seed(config.birdnet_base_url, http)

    species_list = []
    for sci, first_ts, count in rows:
        image_url = get_image_url_from_db(config.birdnet_db_path, sci)
        species_list.append(Species(
            common_name=_name_cache.get(sci),
            scientific_name=sci,
            first_seen=_format_time(first_ts, config.timezone),
            detection_count=count,
            image_url=image_url,
        ))

    now = datetime.now(config.timezone).strftime("%-I:%M %p")
    _store.update(species_list, _date_label(config.timezone), now)
    log.info("Store updated: %d species", len(species_list))


def start_background_poller(config: Config) -> None:
    http = requests.Session()
    http.headers["User-Agent"] = "Birdhouse/0.1"

    def loop() -> None:
        while True:
            try:
                _refresh(config, http)
            except Exception:
                log.exception("Unhandled error in refresh loop")
            time.sleep(config.poll_interval)

    t = threading.Thread(target=loop, daemon=True, name="birdhouse-poller")
    t.start()


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

def create_app(config: Optional[Config] = None) -> Flask:
    if config is None:
        config = Config.from_env()

    app = Flask(__name__, template_folder="templates")
    app.config["BIRDHOUSE_CONFIG"] = config

    @app.route("/")
    def index():
        species, date_label, last_updated = _store.snapshot()
        cfg = app.config["BIRDHOUSE_CONFIG"]
        return render_template(
            "index.html",
            species=species,
            date_label=date_label,
            last_updated=last_updated,
            slide_duration=cfg.slide_duration,
        )

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import os
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = Config.from_env()
    start_background_poller(config)
    app = create_app(config)
    app.run(host="0.0.0.0", port=config.port, debug=False)


if __name__ == "__main__":
    main()
