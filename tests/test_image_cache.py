"""Tests for iNaturalist image fetching and disk caching."""

import requests
import responses as rsps_lib

from birdhouse.app import fetch_species_image, _safe_filename

INAT_URL = "https://api.inaturalist.org/v1/taxa"
FAKE_IMAGE_URL = "https://static.inaturalist.org/photos/1/large.jpg"
FAKE_IMAGE_BYTES = b"\xff\xd8\xff"  # minimal JPEG magic bytes


def _inat_response(scientific_name: str, image_url: str = FAKE_IMAGE_URL) -> dict:
    return {
        "results": [{
            "name": scientific_name,
            "default_photo": {"large_url": image_url, "medium_url": image_url},
        }]
    }


class TestSafeFilename:
    def test_replaces_spaces(self):
        assert " " not in _safe_filename("Corvus brachyrhynchos")

    def test_ends_with_jpg(self):
        assert _safe_filename("Corvus brachyrhynchos").endswith(".jpg")

    def test_deterministic(self):
        assert _safe_filename("Corvus brachyrhynchos") == _safe_filename("Corvus brachyrhynchos")

    def test_different_species_different_names(self):
        assert _safe_filename("Corvus brachyrhynchos") != _safe_filename("Haemorhous mexicanus")


@rsps_lib.activate
def test_downloads_and_caches_image(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, json=_inat_response("Corvus brachyrhynchos"))
    rsps_lib.add(rsps_lib.GET, FAKE_IMAGE_URL, body=FAKE_IMAGE_BYTES, content_type="image/jpeg")

    result = fetch_species_image("Corvus brachyrhynchos", tmp_path, requests.Session())

    assert result is not None
    assert (tmp_path / result).exists()
    assert (tmp_path / result).read_bytes() == FAKE_IMAGE_BYTES


@rsps_lib.activate
def test_returns_cached_file_without_network(tmp_path):
    filename = _safe_filename("Corvus brachyrhynchos")
    (tmp_path / filename).write_bytes(FAKE_IMAGE_BYTES)

    fetch_species_image("Corvus brachyrhynchos", tmp_path, requests.Session())

    assert len(rsps_lib.calls) == 0


@rsps_lib.activate
def test_returns_none_when_no_inat_result(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, json={"results": []})
    assert fetch_species_image("Unknown species", tmp_path, requests.Session()) is None


@rsps_lib.activate
def test_returns_none_when_inat_request_fails(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, body=requests.ConnectionError("network error"))
    assert fetch_species_image("Corvus brachyrhynchos", tmp_path, requests.Session()) is None


@rsps_lib.activate
def test_returns_none_when_image_download_fails(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, json=_inat_response("Corvus brachyrhynchos"))
    rsps_lib.add(rsps_lib.GET, FAKE_IMAGE_URL, status=503)
    assert fetch_species_image("Corvus brachyrhynchos", tmp_path, requests.Session()) is None
    assert not any(tmp_path.iterdir())


@rsps_lib.activate
def test_creates_cache_dir_if_missing(tmp_path):
    cache_dir = tmp_path / "nested" / "cache"
    rsps_lib.add(rsps_lib.GET, INAT_URL, json=_inat_response("Corvus brachyrhynchos"))
    rsps_lib.add(rsps_lib.GET, FAKE_IMAGE_URL, body=FAKE_IMAGE_BYTES, content_type="image/jpeg")
    fetch_species_image("Corvus brachyrhynchos", cache_dir, requests.Session())
    assert cache_dir.exists()
