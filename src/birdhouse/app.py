"""
Birdhouse — full-bleed bird species carousel from BirdNET-Go detections.

Polls the BirdNET-Go REST API for today's detections, deduplicates by species,
fetches representative photos from iNaturalist, and serves a single-page
auto-advancing carousel.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from flask import Flask, render_template, send_from_directory

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    birdnet_base_url: str
    port: int
    min_confidence: float
    image_cache_dir: Path
    timezone: ZoneInfo
    poll_interval: int
    slide_duration: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            birdnet_base_url=os.environ.get("BIRDNET_BASE_URL", "http://192.168.1.100:8888").rstrip("/"),
            port=int(os.environ.get("PORT", "8090")),
            min_confidence=float(os.environ.get("MIN_CONFIDENCE", "0.6")),
            image_cache_dir=Path(os.environ.get("IMAGE_CACHE_DIR", "data/image-cache")),
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
    first_seen: str       # "HH:MM" local time
    image_path: Optional[str] = None   # relative path served at /images/<filename>


# ---------------------------------------------------------------------------
# BirdNET-Go client
# ---------------------------------------------------------------------------

def fetch_detections_for_date(base_url: str, date_str: str, session: requests.Session) -> list[dict]:
    """Fetch all detections for date_str (YYYY-MM-DD), paginating as needed."""
    detections: list[dict] = []
    limit = 200
    offset = 0

    while True:
        url = f"{base_url}/api/v2/detections"
        params = {"date": date_str, "limit": limit, "offset": offset}
        try:
            resp = session.get(url, params=params, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.error("BirdNET-Go request failed: %s", exc)
            break

        data = resp.json()
        page = data.get("data") or []
        detections.extend(page)

        total_pages = data.get("total_pages", 1)
        current_page = data.get("current_page", 1)
        if current_page >= total_pages or not page:
            break
        offset += limit

    return detections


def unique_species_from_detections(
    detections: list[dict],
    min_confidence: float,
    tz: ZoneInfo,
) -> list[Species]:
    """
    Filter by confidence, deduplicate by scientificName, sort by first detection.
    Returns one Species per unique scientific name, in first-detection order.
    """
    earliest: dict[str, dict] = {}  # scientific_name → detection record

    for det in detections:
        confidence = det.get("confidence") or 0.0
        if confidence < min_confidence:
            continue

        sci = (det.get("scientificName") or "").strip()
        if not sci:
            continue

        if sci not in earliest:
            earliest[sci] = det
        else:
            # Keep whichever has the earlier timestamp
            if det.get("timestamp", "") < earliest[sci].get("timestamp", ""):
                earliest[sci] = det

    result = []
    for det in sorted(earliest.values(), key=lambda d: d.get("timestamp", "")):
        sci = (det.get("scientificName") or "").strip()
        common = (det.get("commonName") or sci).strip()

        # Format time as "5:24 pm" in local timezone
        ts_str = det.get("timestamp") or ""
        first_seen = _format_time(ts_str, tz)

        result.append(Species(
            common_name=common,
            scientific_name=sci,
            first_seen=first_seen,
        ))

    return result


def _format_time(timestamp: str, tz: ZoneInfo) -> str:
    """Parse an ISO-8601 timestamp and return a friendly local time string."""
    if not timestamp:
        return ""
    try:
        dt = datetime.fromisoformat(timestamp)
        local = dt.astimezone(tz)
        hour = local.hour % 12 or 12
        ampm = "am" if local.hour < 12 else "pm"
        return f"{hour}:{local.minute:02d} {ampm}"
    except (ValueError, TypeError):
        return timestamp


# ---------------------------------------------------------------------------
# iNaturalist image cache
# ---------------------------------------------------------------------------

INATURALIST_API = "https://api.inaturalist.org/v1/taxa"
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _safe_filename(scientific_name: str) -> str:
    return _SAFE_NAME_RE.sub("_", scientific_name) + ".jpg"


def fetch_species_image(
    scientific_name: str,
    cache_dir: Path,
    session: requests.Session,
) -> Optional[str]:
    """
    Return the filename (relative to cache_dir) of a cached species photo,
    fetching from iNaturalist if not already on disk.
    Returns None if no image is available.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(scientific_name)
    dest = cache_dir / filename

    if dest.exists():
        return filename

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
        return None

    if not results:
        log.info("No iNaturalist result for %s", scientific_name)
        return None

    taxon = results[0]
    photo = taxon.get("default_photo") or {}
    image_url = photo.get("large_url") or photo.get("medium_url") or ""

    if not image_url:
        log.info("No photo URL for %s", scientific_name)
        return None

    # Download and cache
    try:
        img_resp = session.get(image_url, timeout=20)
        img_resp.raise_for_status()
        dest.write_bytes(img_resp.content)
        log.info("Cached image for %s → %s", scientific_name, filename)
        return filename
    except requests.RequestException as exc:
        log.warning("Image download failed for %s: %s", scientific_name, exc)
        return None


# ---------------------------------------------------------------------------
# Data store (shared between background thread and Flask)
# ---------------------------------------------------------------------------

@dataclass
class DataStore:
    species: list[Species] = field(default_factory=list)
    date_label: str = ""          # e.g. "Tuesday 13 May 2026"
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

def _today_str(tz: ZoneInfo) -> str:
    return datetime.now(tz).strftime("%Y-%m-%d")


def _date_label(tz: ZoneInfo) -> str:
    return datetime.now(tz).strftime("%A %-d %B %Y")


def _refresh(config: Config, http: requests.Session) -> None:
    """Fetch today's data and update the store."""
    date_str = _today_str(config.timezone)
    log.info("Refreshing detections for %s", date_str)

    detections = fetch_detections_for_date(config.birdnet_base_url, date_str, http)
    species_list = unique_species_from_detections(detections, config.min_confidence, config.timezone)

    # Fetch images (blocking; cached after first fetch)
    for sp in species_list:
        sp.image_path = fetch_species_image(sp.scientific_name, config.image_cache_dir, http)

    now = datetime.now(config.timezone).strftime("%-I:%M %p")
    _store.update(species_list, _date_label(config.timezone), now)
    log.info("Store updated: %d unique species", len(species_list))


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
