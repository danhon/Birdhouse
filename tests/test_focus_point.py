"""Tests for vision-based focal point computation (_get_or_compute_focus)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

import birdhouse.app as app_module
from birdhouse.app import _get_or_compute_focus


@pytest.fixture(autouse=True)
def reset_vision_state():
    """_vision_disabled and _focus_cooldown are module-level singletons."""
    app_module._vision_disabled = False
    app_module._focus_cooldown.clear()
    yield
    app_module._vision_disabled = False
    app_module._focus_cooldown.clear()


def _fake_response(stop_reason="end_turn", text=None):
    content = [SimpleNamespace(type="text", text=text)] if text is not None else []
    return SimpleNamespace(stop_reason=stop_reason, content=content)


def _fake_client(response=None, side_effect=None):
    client = MagicMock()
    if side_effect is not None:
        client.messages.create.side_effect = side_effect
    else:
        client.messages.create.return_value = response
    return client


def _write_image(tmp_path):
    image_path = tmp_path / "Corvus_brachyrhynchos.jpg"
    image_path.write_bytes(b"\xff\xd8\xff")  # minimal JPEG magic bytes
    return image_path


def _auth_error():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(401, request=req)
    return anthropic.AuthenticationError("bad key", response=resp, body=None)


def _rate_limit_error():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(429, request=req)
    return anthropic.RateLimitError("rate limited", response=resp, body=None)


class TestSuccess:
    def test_computes_and_caches_focus(self, tmp_path):
        image_path = _write_image(tmp_path)
        focus_file = tmp_path / "Corvus_brachyrhynchos.jpg.focus"
        text = json.dumps({
            "visible": True,
            "bird_box": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9},
            "focus_x": 0.5,
            "focus_y": 0.3,
        })
        client = _fake_client(_fake_response(text=text))

        result = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client)

        assert result == (0.5, 0.3)
        assert focus_file.exists()
        assert focus_file.read_text(encoding="utf-8") == "0.5000,0.3000"
        client.messages.create.assert_called_once()

    def test_clamps_focus_into_bird_box(self, tmp_path):
        image_path = _write_image(tmp_path)
        focus_file = tmp_path / "Corvus_brachyrhynchos.jpg.focus"
        text = json.dumps({
            "visible": True,
            "bird_box": {"x0": 0.2, "y0": 0.2, "x1": 0.6, "y1": 0.6},
            "focus_x": 0.05,   # outside the box -- should clamp to x0
            "focus_y": 0.9,    # outside the box -- should clamp to y1
        })
        client = _fake_client(_fake_response(text=text))

        result = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client)

        assert result == (0.2, 0.6)

    def test_uses_coords_even_when_not_visible(self, tmp_path):
        image_path = _write_image(tmp_path)
        focus_file = tmp_path / "Corvus_brachyrhynchos.jpg.focus"
        text = json.dumps({
            "visible": False,
            "bird_box": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9},
            "focus_x": 0.4,
            "focus_y": 0.4,
        })
        client = _fake_client(_fake_response(text=text))

        result = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client)

        assert result == (0.4, 0.4)


class TestCaching:
    def test_returns_cached_focus_without_calling_api(self, tmp_path):
        image_path = _write_image(tmp_path)
        focus_file = tmp_path / "Corvus_brachyrhynchos.jpg.focus"
        focus_file.write_text("0.42,0.33", encoding="utf-8")
        client = _fake_client()

        result = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client)

        assert result == (0.42, 0.33)
        client.messages.create.assert_not_called()

    def test_recomputes_on_malformed_cache_file(self, tmp_path):
        image_path = _write_image(tmp_path)
        focus_file = tmp_path / "Corvus_brachyrhynchos.jpg.focus"
        focus_file.write_text("not-a-number", encoding="utf-8")
        text = json.dumps({
            "visible": True,
            "bird_box": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9},
            "focus_x": 0.5,
            "focus_y": 0.5,
        })
        client = _fake_client(_fake_response(text=text))

        result = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client)

        assert result == (0.5, 0.5)
        client.messages.create.assert_called_once()


class TestFailureHandling:
    def test_refusal_returns_none_and_applies_cooldown(self, tmp_path):
        image_path = _write_image(tmp_path)
        focus_file = tmp_path / "Corvus_brachyrhynchos.jpg.focus"
        client = _fake_client(_fake_response(stop_reason="refusal"))

        result = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client)

        assert result is None
        assert not focus_file.exists()
        assert "Corvus brachyrhynchos" in app_module._focus_cooldown

    def test_malformed_json_returns_none_and_applies_cooldown(self, tmp_path):
        image_path = _write_image(tmp_path)
        focus_file = tmp_path / "Corvus_brachyrhynchos.jpg.focus"
        client = _fake_client(_fake_response(text="not json"))

        result = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client)

        assert result is None
        assert not focus_file.exists()
        assert "Corvus brachyrhynchos" in app_module._focus_cooldown

    def test_auth_error_disables_vision_permanently(self, tmp_path):
        image_path = _write_image(tmp_path)
        focus_file = tmp_path / "Corvus_brachyrhynchos.jpg.focus"
        client = _fake_client(side_effect=_auth_error())

        result = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client)

        assert result is None
        assert app_module._vision_disabled is True

        # A second call, even for a different species, must not attempt the API.
        client2 = _fake_client()
        result2 = _get_or_compute_focus("Haemorhous mexicanus", image_path, focus_file, client2)
        assert result2 is None
        client2.messages.create.assert_not_called()

    def test_rate_limit_error_applies_cooldown_not_permanent_disable(self, tmp_path):
        image_path = _write_image(tmp_path)
        focus_file = tmp_path / "Corvus_brachyrhynchos.jpg.focus"
        client = _fake_client(side_effect=_rate_limit_error())

        result = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client)

        assert result is None
        assert app_module._vision_disabled is False
        assert "Corvus brachyrhynchos" in app_module._focus_cooldown

        # Second attempt within the cooldown window must not call the API again.
        client2 = _fake_client()
        result2 = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client2)
        assert result2 is None
        client2.messages.create.assert_not_called()

    def test_connection_error_applies_cooldown(self, tmp_path):
        image_path = _write_image(tmp_path)
        focus_file = tmp_path / "Corvus_brachyrhynchos.jpg.focus"
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        client = _fake_client(side_effect=anthropic.APIConnectionError(request=req))

        result = _get_or_compute_focus("Corvus brachyrhynchos", image_path, focus_file, client)

        assert result is None
        assert "Corvus brachyrhynchos" in app_module._focus_cooldown
