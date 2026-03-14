"""Tests for manimator.topic_templates — structures, schemas, and prompt generation."""

import json

from manimator.topic_templates import (
    STRUCTURES,
    DOMAIN_TEMPLATES,
    SCENE_SCHEMAS,
    get_storyboard_prompt,
    get_example_storyboard,
)


class TestDataStructures:
    """Verify the module-level dictionaries are populated and well-formed."""

    def test_structures_is_non_empty_dict(self):
        assert isinstance(STRUCTURES, dict)
        assert len(STRUCTURES) > 0

    def test_domain_templates_is_non_empty_dict(self):
        assert isinstance(DOMAIN_TEMPLATES, dict)
        assert len(DOMAIN_TEMPLATES) > 0

    def test_scene_schemas_is_non_empty_dict(self):
        assert isinstance(SCENE_SCHEMAS, dict)
        assert len(SCENE_SCHEMAS) > 0

    def test_every_structure_has_scenes_list(self):
        for key, val in STRUCTURES.items():
            assert "scenes" in val, f"Structure {key!r} missing 'scenes'"
            assert isinstance(val["scenes"], list)

    def test_every_scene_schema_has_example(self):
        for key, val in SCENE_SCHEMAS.items():
            assert "example" in val, f"Schema {key!r} missing 'example'"
            assert isinstance(val["example"], dict)


class TestGetStoryboardPrompt:
    """Verify prompt generation returns a string containing the topic."""

    def test_returns_string(self):
        result = get_storyboard_prompt("photosynthesis")
        assert isinstance(result, str)

    def test_topic_appears_in_prompt(self):
        topic = "quantum entanglement"
        result = get_storyboard_prompt(topic)
        assert topic in result

    def test_domain_overrides_theme(self):
        result = get_storyboard_prompt(
            "CRISPR", domain="biology_mechanism"
        )
        # biology_mechanism uses npg theme
        assert "npg" in result

    def test_portrait_format_note(self):
        result = get_storyboard_prompt(
            "test", format_type="instagram_reel"
        )
        assert "PORTRAIT" in result


class TestGetExampleStoryboard:
    """Verify example storyboards are valid JSON-serialisable dicts."""

    def test_returns_dict_with_meta_and_scenes(self):
        sb = get_example_storyboard("biology_reel")
        assert "meta" in sb
        assert "scenes" in sb

    def test_serialises_to_valid_json(self):
        sb = get_example_storyboard("biology_reel")
        raw = json.dumps(sb)
        parsed = json.loads(raw)
        assert "meta" in parsed
        assert "scenes" in parsed

    def test_fallback_for_unknown_domain(self):
        sb = get_example_storyboard("nonexistent_domain")
        # Should fall back to biology_reel
        assert "meta" in sb
        assert "scenes" in sb

    def test_cs_reel_example(self):
        sb = get_example_storyboard("cs_reel")
        assert sb["meta"]["color_theme"] == "tol_bright"
