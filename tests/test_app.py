"""Tests for the Flask app routes."""

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
