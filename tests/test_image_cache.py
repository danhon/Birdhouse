"""Tests for iNaturalist image fetching and disk caching."""

import pytest
import responses as rsps_lib
from pathlib import Path

from birdhouse.app import fetch_species_image, _safe_filename
import requests


INAT_URL = "https://api.inaturalist.org/v1/taxa"
FAKE_IMAGE_URL = "https://static.inaturalist.org/photos/1/medium.jpg"
FAKE_IMAGE_BYTES = b"\xff\xd8\xff"  # minimal JPEG magic bytes


def _inat_response(scientific_name: str, image_url: str = FAKE_IMAGE_URL) -> dict:
    return {
        "results": [
            {
                "name": scientific_name,
                "default_photo": {
                    "large_url": image_url,
                    "medium_url": image_url,
                },
            }
        ]
    }


# ---------------------------------------------------------------------------
# _safe_filename
# ---------------------------------------------------------------------------

class TestSafeFilename:
    def test_replaces_spaces(self):
        assert " " not in _safe_filename("Corvus brachyrhynchos")

    def test_ends_with_jpg(self):
        assert _safe_filename("Corvus brachyrhynchos").endswith(".jpg")

    def test_deterministic(self):
        assert _safe_filename("Corvus brachyrhynchos") == _safe_filename("Corvus brachyrhynchos")

    def test_different_species_different_names(self):
        assert _safe_filename("Corvus brachyrhynchos") != _safe_filename("Haemorhous mexicanus")


# ---------------------------------------------------------------------------
# fetch_species_image
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_downloads_and_caches_image(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, json=_inat_response("Corvus brachyrhynchos"))
    rsps_lib.add(rsps_lib.GET, FAKE_IMAGE_URL, body=FAKE_IMAGE_BYTES, content_type="image/jpeg")

    session = requests.Session()
    filename = fetch_species_image("Corvus brachyrhynchos", tmp_path, session)

    assert filename is not None
    assert (tmp_path / filename).exists()
    assert (tmp_path / filename).read_bytes() == FAKE_IMAGE_BYTES


@rsps_lib.activate
def test_returns_cached_file_without_network(tmp_path):
    # Pre-populate cache
    filename = _safe_filename("Corvus brachyrhynchos")
    (tmp_path / filename).write_bytes(FAKE_IMAGE_BYTES)

    session = requests.Session()
    result = fetch_species_image("Corvus brachyrhynchos", tmp_path, session)

    assert result == filename
    # No network calls should have been made
    assert len(rsps_lib.calls) == 0


@rsps_lib.activate
def test_returns_none_when_no_inat_result(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, json={"results": []})

    session = requests.Session()
    result = fetch_species_image("Unknown species", tmp_path, session)

    assert result is None
    assert not any(tmp_path.iterdir())


@rsps_lib.activate
def test_returns_none_when_inat_request_fails(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, body=requests.ConnectionError("network error"))

    session = requests.Session()
    result = fetch_species_image("Corvus brachyrhynchos", tmp_path, session)

    assert result is None


@rsps_lib.activate
def test_returns_none_when_image_download_fails(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, json=_inat_response("Corvus brachyrhynchos"))
    rsps_lib.add(rsps_lib.GET, FAKE_IMAGE_URL, status=503)

    session = requests.Session()
    result = fetch_species_image("Corvus brachyrhynchos", tmp_path, session)

    assert result is None
    assert not any(tmp_path.iterdir())


@rsps_lib.activate
def test_returns_none_when_no_photo_url(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, json={
        "results": [{"name": "Corvus brachyrhynchos", "default_photo": None}]
    })

    session = requests.Session()
    result = fetch_species_image("Corvus brachyrhynchos", tmp_path, session)

    assert result is None


@rsps_lib.activate
def test_creates_cache_dir_if_missing(tmp_path):
    cache_dir = tmp_path / "nested" / "cache"
    assert not cache_dir.exists()

    rsps_lib.add(rsps_lib.GET, INAT_URL, json=_inat_response("Corvus brachyrhynchos"))
    rsps_lib.add(rsps_lib.GET, FAKE_IMAGE_URL, body=FAKE_IMAGE_BYTES, content_type="image/jpeg")

    session = requests.Session()
    fetch_species_image("Corvus brachyrhynchos", cache_dir, session)

    assert cache_dir.exists()
