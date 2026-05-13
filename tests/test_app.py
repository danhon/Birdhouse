"""Tests for the Flask app routes."""

import pytest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from birdhouse.app import Config, DataStore, Species, create_app
from pathlib import Path


@pytest.fixture
def config(tmp_path):
    return Config(
        birdnet_base_url="http://localhost:8888",
        port=8090,
        min_confidence=0.6,
        image_cache_dir=tmp_path / "images",
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


# ---------------------------------------------------------------------------
# Route: /
# ---------------------------------------------------------------------------

class TestIndexRoute:
    def test_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_empty_state_shows_no_birds_message(self, client):
        response = client.get("/")
        assert b"No birds yet today" in response.data

    def test_species_rendered_when_store_has_data(self, client):
        import birdhouse.app as app_module
        app_module._store.update(
            species=[
                Species("American Crow", "Corvus brachyrhynchos", "8:00 am"),
                Species("House Finch", "Haemorhous mexicanus", "9:00 am"),
            ],
            date_label="Monday 12 May 2026",
            last_updated="9:05 am",
        )
        response = client.get("/")
        assert b"American Crow" in response.data
        assert b"Corvus brachyrhynchos" in response.data
        assert b"House Finch" in response.data
        assert b"2 species today" in response.data

        # Reset store
        app_module._store.update([], "", "")

    def test_date_label_in_response(self, client):
        import birdhouse.app as app_module
        app_module._store.update(
            species=[Species("American Crow", "Corvus brachyrhynchos", "8:00 am")],
            date_label="Tuesday 13 May 2026",
            last_updated="8:05 am",
        )
        response = client.get("/")
        assert b"Tuesday 13 May 2026" in response.data
        app_module._store.update([], "", "")

    def test_slide_duration_in_response(self, client):
        import birdhouse.app as app_module
        app_module._store.update(
            species=[Species("American Crow", "Corvus brachyrhynchos", "8:00 am")],
            date_label="Monday 12 May 2026",
            last_updated="8:05 am",
        )
        response = client.get("/")
        # slide_duration=8 → 8000ms in JS
        assert b"8000" in response.data
        app_module._store.update([], "", "")

    def test_image_tag_rendered_when_image_path_set(self, client):
        import birdhouse.app as app_module
        app_module._store.update(
            species=[
                Species("American Crow", "Corvus brachyrhynchos", "8:00 am",
                        image_path="Corvus_brachyrhynchos.jpg"),
            ],
            date_label="Monday 12 May 2026",
            last_updated="8:05 am",
        )
        response = client.get("/")
        assert b'src="/images/Corvus_brachyrhynchos.jpg"' in response.data
        app_module._store.update([], "", "")

    def test_no_image_tag_when_image_path_none(self, client):
        import birdhouse.app as app_module
        app_module._store.update(
            species=[Species("American Crow", "Corvus brachyrhynchos", "8:00 am", image_path=None)],
            date_label="Monday 12 May 2026",
            last_updated="8:05 am",
        )
        response = client.get("/")
        assert b'slide__no-photo' in response.data
        app_module._store.update([], "", "")


# ---------------------------------------------------------------------------
# Route: /images/<filename>
# ---------------------------------------------------------------------------

class TestImagesRoute:
    def test_serves_cached_image(self, client, config):
        config.image_cache_dir.mkdir(parents=True, exist_ok=True)
        img = config.image_cache_dir / "test_bird.jpg"
        img.write_bytes(b"\xff\xd8\xff")  # minimal JPEG

        response = client.get("/images/test_bird.jpg")
        assert response.status_code == 200
        assert response.data == b"\xff\xd8\xff"

    def test_404_for_missing_image(self, client, config):
        config.image_cache_dir.mkdir(parents=True, exist_ok=True)
        response = client.get("/images/nonexistent.jpg")
        assert response.status_code == 404
