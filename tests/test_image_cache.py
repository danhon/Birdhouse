"""Tests for iNaturalist image fetching and disk caching."""

import requests
import responses as rsps_lib

from birdhouse.app import fetch_species_image, _safe_filename

INAT_URL = "https://api.inaturalist.org/v1/taxa"
FAKE_IMAGE_URL = "https://static.inaturalist.org/photos/1/large.jpg"
FAKE_IMAGE_BYTES = b"\xff\xd8\xff"  # minimal JPEG magic bytes


def _inat_response(
    scientific_name: str,
    image_url: str = FAKE_IMAGE_URL,
    common_name: str = "Test Bird",
    taxon_id: int = 12727,
) -> dict:
    return {
        "results": [{
            "id": taxon_id,
            "name": scientific_name,
            "preferred_common_name": common_name,
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
    rsps_lib.add(rsps_lib.GET, INAT_URL, json=_inat_response("Corvus brachyrhynchos", common_name="American Crow"))
    rsps_lib.add(rsps_lib.GET, FAKE_IMAGE_URL, body=FAKE_IMAGE_BYTES, content_type="image/jpeg")

    image_path, common_name, inat_id, focus = fetch_species_image("Corvus brachyrhynchos", tmp_path, requests.Session())

    assert image_path is not None
    assert (tmp_path / image_path).exists()
    assert (tmp_path / image_path).read_bytes() == FAKE_IMAGE_BYTES
    assert common_name == "American Crow"
    assert inat_id == 12727
    assert focus is None   # no vision_client supplied


@rsps_lib.activate
def test_returns_cached_file_without_network(tmp_path):
    filename = _safe_filename("Corvus brachyrhynchos")
    (tmp_path / filename).write_bytes(FAKE_IMAGE_BYTES)
    (tmp_path / (filename + ".name")).write_text("American Crow", encoding="utf-8")
    (tmp_path / (filename + ".id")).write_text("12727", encoding="utf-8")

    image_path, common_name, inat_id, focus = fetch_species_image("Corvus brachyrhynchos", tmp_path, requests.Session())

    assert len(rsps_lib.calls) == 0
    assert image_path == filename
    assert common_name == "American Crow"
    assert inat_id == 12727
    assert focus is None


@rsps_lib.activate
def test_returns_none_when_no_inat_result(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, json={"results": []})
    image_path, common_name, inat_id, focus = fetch_species_image("Unknown species", tmp_path, requests.Session())
    assert image_path is None
    assert common_name is None
    assert inat_id is None
    assert focus is None


@rsps_lib.activate
def test_returns_none_when_inat_request_fails(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, body=requests.ConnectionError("network error"))
    image_path, common_name, inat_id, focus = fetch_species_image("Corvus brachyrhynchos", tmp_path, requests.Session())
    assert image_path is None
    assert common_name is None
    assert inat_id is None
    assert focus is None


@rsps_lib.activate
def test_returns_none_image_but_common_name_when_download_fails(tmp_path):
    rsps_lib.add(rsps_lib.GET, INAT_URL, json=_inat_response("Corvus brachyrhynchos", common_name="American Crow"))
    rsps_lib.add(rsps_lib.GET, FAKE_IMAGE_URL, status=503)
    image_path, common_name, inat_id, focus = fetch_species_image("Corvus brachyrhynchos", tmp_path, requests.Session())
    assert image_path is None
    assert common_name == "American Crow"   # name still returned even if image fails
    assert inat_id == 12727
    assert focus is None
    assert not (tmp_path / _safe_filename("Corvus brachyrhynchos")).exists()


@rsps_lib.activate
def test_creates_cache_dir_if_missing(tmp_path):
    cache_dir = tmp_path / "nested" / "cache"
    rsps_lib.add(rsps_lib.GET, INAT_URL, json=_inat_response("Corvus brachyrhynchos"))
    rsps_lib.add(rsps_lib.GET, FAKE_IMAGE_URL, body=FAKE_IMAGE_BYTES, content_type="image/jpeg")
    fetch_species_image("Corvus brachyrhynchos", cache_dir, requests.Session())
    assert cache_dir.exists()


@rsps_lib.activate
def test_returns_common_name_even_without_photo(tmp_path):
    """iNaturalist has a name but no photo URL."""
    rsps_lib.add(rsps_lib.GET, INAT_URL, json={
        "results": [{"name": "Corvus brachyrhynchos", "preferred_common_name": "American Crow",
                     "default_photo": None}]
    })
    image_path, common_name, inat_id, focus = fetch_species_image("Corvus brachyrhynchos", tmp_path, requests.Session())
    assert image_path is None
    assert common_name == "American Crow"
    assert inat_id is None
    assert focus is None
