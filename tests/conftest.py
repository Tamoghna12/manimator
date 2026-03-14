"""Shared fixtures for manimator test suite."""

import pytest

from manimator.web.app import app as flask_app
from manimator.config import THEMES


# ── Sample storyboard dicts ────────────────────────────────────────────────


@pytest.fixture
def valid_storyboard_dict():
    """A minimal but complete storyboard that should pass validation."""
    return {
        "meta": {
            "title": "Test Storyboard",
            "author": "Pytest",
            "resolution": [1920, 1080],
            "fps": 60,
            "output_format": "webm",
            "color_theme": "wong",
            "format": "presentation",
        },
        "scenes": [
            {
                "type": "title",
                "id": "intro",
                "title": "Test Title",
                "subtitle": "A subtitle",
            },
            {
                "type": "bullet_list",
                "id": "points",
                "header": "Key Points",
                "items": ["Point A", "Point B", "Point C"],
            },
            {
                "type": "closing",
                "id": "end",
                "title": "References",
                "references": ["Author (2024) Journal"],
            },
        ],
    }


@pytest.fixture
def storyboard_missing_meta():
    """Storyboard dict with meta omitted entirely."""
    return {
        "scenes": [
            {"type": "title", "id": "t", "title": "Hello"},
        ],
    }


@pytest.fixture
def storyboard_invalid_scene_type():
    """Storyboard with an unrecognised scene type."""
    return {
        "meta": {"title": "Bad"},
        "scenes": [
            {"type": "nonexistent_type", "id": "x"},
        ],
    }


@pytest.fixture
def storyboard_empty_scenes():
    """Storyboard with an empty scenes list."""
    return {
        "meta": {"title": "Empty"},
        "scenes": [],
    }


@pytest.fixture
def wong_theme():
    """Return the wong color theme dict."""
    return THEMES["wong"]


# ── Flask test client ──────────────────────────────────────────────────────


@pytest.fixture
def client():
    """Flask test client with testing mode enabled."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
