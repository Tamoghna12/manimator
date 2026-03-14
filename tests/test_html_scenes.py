"""Tests for manimator.portrait.html_scenes — HTML rendering per scene type."""

import pytest

from manimator.portrait.html_scenes import render_scene_html
from manimator.topic_templates import SCENE_SCHEMAS
from manimator.config import THEMES


@pytest.fixture
def default_theme():
    return THEMES["wong"]


class TestRenderSceneHtml:
    """For every scene type in SCENE_SCHEMAS, render_scene_html should
    return a non-empty HTML string when given the example data."""

    @pytest.fixture(params=list(SCENE_SCHEMAS.keys()))
    def scene_type(self, request):
        return request.param

    def test_renders_non_empty_html(self, scene_type, default_theme):
        example_data = SCENE_SCHEMAS[scene_type]["example"]
        html = render_scene_html(example_data, default_theme)
        assert isinstance(html, str), (
            f"render_scene_html returned {type(html)} for {scene_type!r}"
        )
        assert len(html) > 0, (
            f"render_scene_html returned empty string for {scene_type!r}"
        )

    def test_html_contains_doctype_or_body(self, scene_type, default_theme):
        """Basic structural check: output should contain HTML markers."""
        example_data = SCENE_SCHEMAS[scene_type]["example"]
        html = render_scene_html(example_data, default_theme)
        html_lower = html.lower()
        assert "<!doctype" in html_lower or "<body" in html_lower or "<div" in html_lower, (
            f"Output for {scene_type!r} lacks basic HTML structure"
        )


class TestUnknownSceneType:
    def test_unknown_type_returns_empty_string(self):
        result = render_scene_html({"type": "nonexistent"}, THEMES["wong"])
        assert result == ""
