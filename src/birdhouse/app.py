"""
Birdhouse — full-bleed bird species carousel from BirdNET-Go detections.

Queries the BirdNET-Go SQLite database directly for accurate per-day counts
and first-detection times. Fetches species photos from iNaturalist (cached
to disk). Fetches common names from the BirdNET-Go REST API.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, render_template, send_from_directory

log = logging.getLogger(__name__)

INATURALIST_API = "https://api.inaturalist.org/v1/taxa"
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    birdnet_base_url: str
    birdnet_db_path: Path
    port: int
    image_cache_dir: Path
    min_confidence: float
    timezone: ZoneInfo
    poll_interval: int
    slide_duration: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            birdnet_base_url=os.environ.get("BIRDNET_BASE_URL", "http://192.168.1.100:8888").rstrip("/"),
            birdnet_db_path=Path(os.environ.get("BIRDNET_DB_PATH", "/home/danhon/birdnet-go-app/data/birdnet.db")),
            port=int(os.environ.get("PORT", "8090")),
            image_cache_dir=Path(os.environ.get("IMAGE_CACHE_DIR", "data/image-cache")),
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
    image_path: Optional[str] = None   # filename served at /images/<filename>
    last_seen: str = ""    # "5:24 pm" local time; equals first_seen when count == 1


# ---------------------------------------------------------------------------
# BirdNET-Go database
# ---------------------------------------------------------------------------

def _day_bounds(tz: ZoneInfo) -> tuple[int, int]:
    """Return (start_ts, end_ts) Unix timestamps for today in the given timezone."""
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return int(start.timestamp()), int(end.timestamp())


def _db_connect(db_path: Path) -> sqlite3.Connection:
    """
    Open the BirdNET-Go DB read-only with immutable=1 so SQLite skips all
    locking. Safe because BirdNET-Go is the sole writer. Also works when the
    DB is on a network filesystem (SMB/NFS) where WAL-mode locking fails.
    """
    uri = f"file:{db_path}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def query_today_from_db(
    db_path: Path,
    tz: ZoneInfo,
    min_confidence: float = 0.0,
) -> list[tuple[str, int, int, int]]:
    """
    Query BirdNET-Go's SQLite database for today's species.

    Returns a list of (scientific_name, first_seen_unix_ts, last_seen_unix_ts,
    detection_count) sorted by first detection time ascending, filtered to
    detections at or above min_confidence.
    """
    ts_start, ts_end = _day_bounds(tz)
    try:
        conn = _db_connect(db_path)
        rows = conn.execute(
            """
            SELECT l.scientific_name,
                   MIN(d.detected_at) AS first_seen,
                   MAX(d.detected_at) AS last_seen,
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
        return [(r["scientific_name"], r["first_seen"], r["last_seen"], r["n"]) for r in rows]
    except Exception as exc:
        log.error("DB query failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# iNaturalist image cache
# ---------------------------------------------------------------------------

def _safe_filename(scientific_name: str) -> str:
    return _SAFE_NAME_RE.sub("_", scientific_name) + ".jpg"


def fetch_species_image(
    scientific_name: str,
    cache_dir: Path,
    session: requests.Session,
) -> tuple[Optional[str], Optional[str]]:
    """
    Return (image_filename, common_name) for the given species.

    image_filename is the filename (relative to cache_dir) of a cached photo,
    fetched from iNaturalist if not already on disk; None if unavailable.

    common_name is the preferred_common_name from iNaturalist, available
    whenever the API is called (i.e. not when served from disk cache); None
    if unavailable or served from disk.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(scientific_name)
    dest = cache_dir / filename

    if dest.exists():
        return filename, None

    # Look up taxon on iNaturalist
    try:
        resp = session.get(
            INATURALIST_API,
            params={"q": scientific_name, "rank": "species", "per_page": 1},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except requests.RequestException as exc:
        log.warning("iNaturalist lookup failed for %s: %s", scientific_name, exc)
        return None, None

    if not results:
        log.info("No iNaturalist result for %s", scientific_name)
        return None, None

    taxon = results[0]
    inat_common = (taxon.get("preferred_common_name") or "").strip() or None

    photo = taxon.get("default_photo") or {}
    image_url = photo.get("large_url") or photo.get("medium_url") or ""

    if not image_url:
        log.info("No photo URL for %s", scientific_name)
        return None, inat_common

    try:
        img_resp = session.get(image_url, timeout=20)
        img_resp.raise_for_status()
        dest.write_bytes(img_resp.content)
        log.info("Cached iNaturalist image for %s → %s", scientific_name, filename)
        return filename, inat_common
    except requests.RequestException as exc:
        log.warning("Image download failed for %s: %s", scientific_name, exc)
        return None, inat_common


# ---------------------------------------------------------------------------
# Common name cache
# ---------------------------------------------------------------------------

class CommonNameCache:
    """
    Lazy in-memory cache mapping scientific_name → common_name.
    Populated from the BirdNET-Go REST API. Falls back to scientific name.
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

    def set(self, scientific_name: str, common_name: str) -> None:
        with self._lock:
            self._cache[scientific_name] = common_name

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
# Data store
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
    """Fetch today's data from the DB, images from iNaturalist, update store."""
    log.info("Refreshing from DB: %s", config.birdnet_db_path)

    rows = query_today_from_db(config.birdnet_db_path, config.timezone, config.min_confidence)
    log.info("DB returned %d unique species", len(rows))

    # Top up the common name cache for any species we haven't seen before
    unknown = _name_cache.missing([sci for sci, _, _ in rows])
    if unknown:
        _name_cache.seed(config.birdnet_base_url, http)

    species_list = []
    for sci, first_ts, last_ts, count in rows:
        image_path, inat_common = fetch_species_image(sci, config.image_cache_dir, http)
        # Seed cache with iNaturalist common name when BirdNET-Go API didn't have it
        if inat_common and _name_cache.get(sci) == sci:
            _name_cache.set(sci, inat_common)
        species_list.append(Species(
            common_name=_name_cache.get(sci),
            scientific_name=sci,
            first_seen=_format_time(first_ts, config.timezone),
            last_seen=_format_time(last_ts, config.timezone),
            detection_count=count,
            image_path=image_path,
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
            poll_interval=cfg.poll_interval,
        )

    @app.route("/data.json")
    def data_json():
        species, date_label, last_updated = _store.snapshot()
        return jsonify({
            "date_label": date_label,
            "species_count": len(species),
            "last_updated": last_updated,
        })

    @app.route("/images/<path:filename>")
    def images(filename: str):
        cfg = app.config["BIRDHOUSE_CONFIG"]
        return send_from_directory(cfg.image_cache_dir.resolve(), filename)

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = Config.from_env()
    config.image_cache_dir.mkdir(parents=True, exist_ok=True)
    start_background_poller(config)
    app = create_app(config)
    app.run(host="0.0.0.0", port=config.port, debug=False)


if __name__ == "__main__":
    main()
