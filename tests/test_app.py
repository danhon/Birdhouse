"""Tests for the Flask app routes."""

import re

import pytest
from zoneinfo import ZoneInfo
from pathlib import Path

from birdhouse.app import Config, DataStore, Species, create_app
import birdhouse.app as app_module


@pytest.fixture
def config(tmp_path):
    return Config(
        birdnet_base_url="http://localhost:8888",
        birdnet_db_path=tmp_path / "birdnet.db",
        port=8090,
        image_cache_dir=tmp_path / "images",
        min_confidence=0.6,
        timezone=ZoneInfo("America/Los_Angeles"),
        poll_interval=60,
        slide_duration=8,
        vision_enabled=False,
    )


@pytest.fixture
def app(config):
    return create_app(config)


@pytest.fixture
def client(app):
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_store():
    """Reset the global store before each test."""
    app_module._store.update([], "", "")
    yield
    app_module._store.update([], "", "")


def _load_store(species_list, date_label="Monday 12 May 2026"):
    app_module._store.update(species_list, date_label, "8:05 am")


# ---------------------------------------------------------------------------
# Route: /
# ---------------------------------------------------------------------------

class TestIndexRoute:
    def test_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_empty_state_shows_no_birds_message(self, client):
        assert b"No birds yet today" in client.get("/").data

    def test_species_name_rendered(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 5)])
        data = client.get("/").data
        assert b"American Crow" in data
        assert b"Corvus brachyrhynchos" in data

    def test_species_count_in_header(self, client):
        _load_store([
            Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3),
            Species("House Finch",   "Haemorhous mexicanus",  "9:00 am", 7),
        ])
        assert b"2 species today" in client.get("/").data

    def test_date_label_rendered(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 1)],
                    date_label="Tuesday 13 May 2026")
        assert b"Tuesday 13 May 2026" in client.get("/").data

    def test_slide_duration_in_js(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 1)])
        assert b"8000" in client.get("/").data

    def test_detection_count_plural(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 5)])
        assert b"detected 5 times today" in client.get("/").data

    def test_detection_count_singular(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 1)])
        assert b"detected once today" in client.get("/").data

    def test_image_path_rendered_when_set(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3,
                             image_path="Corvus_brachyrhynchos.jpg")])
        assert b'src="/images/Corvus_brachyrhynchos.jpg"' in client.get("/").data

    def test_no_photo_placeholder_when_no_image(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3,
                             image_path=None)])
        assert b"slide__no-photo" in client.get("/").data

    def test_last_seen_rendered(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 5,
                             last_seen="2:34 pm")])
        assert b"last seen 2:34 pm" in client.get("/").data

    def test_last_seen_shown_for_single_detection(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 1,
                             last_seen="8:00 am")])
        data = client.get("/").data
        assert b"detected once today" in data
        assert b"last seen 8:00 am" in data


# ---------------------------------------------------------------------------
# Species list overlay
# ---------------------------------------------------------------------------

def _overlay_html(data: bytes) -> str:
    """Return just the overlay's markup, so slide content can't leak into checks."""
    html = data.decode()
    start = html.index('id="species-overlay"')
    end = html.index("<!-- /overlay -->", start)
    return html[start:end]


class TestSpeciesOverlay:
    def test_count_is_a_button(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3)])
        data = client.get("/").data.decode()
        assert re.search(r'<button[^>]*id="species-count"', data)
        assert "1 species today" in data

    def test_one_row_per_species_in_carousel_order(self, client):
        _load_store([
            Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3),
            Species("House Finch",   "Haemorhous mexicanus",  "9:00 am", 7),
        ])
        overlay = _overlay_html(client.get("/").data)
        assert re.findall(r'class="overlay__row[^"]*" data-index="(\d+)"', overlay) == ["0", "1"]
        assert overlay.index("American Crow") < overlay.index("House Finch")

    def test_row_thumbnail_matches_slide(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3,
                             image_path="Corvus_brachyrhynchos.jpg", focus_x=0.33, focus_y=0.21)])
        overlay = _overlay_html(client.get("/").data)
        assert 'src="/images/Corvus_brachyrhynchos.jpg"' in overlay
        assert "object-position: 33.0% 21.0%" in overlay

    def test_row_placeholder_without_image(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3,
                             image_path=None)])
        assert "overlay__thumb--empty" in _overlay_html(client.get("/").data)

    def test_row_count_once_and_times(self, client):
        _load_store([
            Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 1),
            Species("House Finch",   "Haemorhous mexicanus",  "9:00 am", 212),
        ])
        overlay = _overlay_html(client.get("/").data)
        assert ">once<" in overlay
        assert ">212×<" in overlay

    def test_row_shows_first_seen_and_scientific(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3)])
        overlay = _overlay_html(client.get("/").data)
        assert "8:00 am" in overlay
        assert "Corvus brachyrhynchos" in overlay

    def test_overlay_has_no_inaturalist_links(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3,
                             inat_id=123)])
        overlay = _overlay_html(client.get("/").data)
        assert "inaturalist.org" not in overlay
        assert "<a " not in overlay

    def test_overlay_closed_by_default(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3)])
        data = client.get("/").data.decode()
        assert re.search(r'id="species-overlay"[^>]*\bhidden\b', data)

    def test_no_overlay_in_empty_state(self, client):
        assert b"species-overlay" not in client.get("/").data


# ---------------------------------------------------------------------------
# Route: /data.json
# ---------------------------------------------------------------------------

class TestDataJsonRoute:
    def test_returns_200(self, client):
        assert client.get("/data.json").status_code == 200

    def test_returns_json(self, client):
        resp = client.get("/data.json")
        assert resp.content_type == "application/json"

    def test_empty_store(self, client):
        data = client.get("/data.json").get_json()
        assert data["species_count"] == 0
        assert data["date_label"] == ""

    def test_species_count(self, client):
        _load_store([
            Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3),
            Species("House Finch",   "Haemorhous mexicanus",  "9:00 am", 7),
        ])
        data = client.get("/data.json").get_json()
        assert data["species_count"] == 2

    def test_date_label(self, client):
        _load_store(
            [Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 1)],
            date_label="Wednesday 13 May 2026",
        )
        data = client.get("/data.json").get_json()
        assert data["date_label"] == "Wednesday 13 May 2026"

    def test_last_updated_present(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 1)])
        data = client.get("/data.json").get_json()
        assert "last_updated" in data


class TestIcons:
    @pytest.mark.parametrize("path", [
        "/favicon.ico",
        "/apple-touch-icon.png",
        "/apple-touch-icon-precomposed.png",
    ])
    def test_icon_served(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.data
