"""Tests for manimator.schema — Storyboard Pydantic validation."""

import pytest
from pydantic import ValidationError

from manimator.schema import Storyboard


class TestStoryboardValidation:
    """Verify that the Storyboard model accepts valid data and rejects invalid data."""

    def test_valid_storyboard_passes(self, valid_storyboard_dict):
        sb = Storyboard(**valid_storyboard_dict)
        assert sb.meta.title == "Test Storyboard"
        assert len(sb.scenes) == 3

    def test_missing_meta_fails(self, storyboard_missing_meta):
        with pytest.raises(ValidationError):
            Storyboard(**storyboard_missing_meta)

    def test_invalid_scene_type_fails(self, storyboard_invalid_scene_type):
        with pytest.raises(ValidationError):
            Storyboard(**storyboard_invalid_scene_type)

    def test_empty_scenes_list_accepted(self, storyboard_empty_scenes):
        """An empty scenes list is structurally valid per the Pydantic model
        (list[SceneSpec] allows length 0).  The model should not raise."""
        sb = Storyboard(**storyboard_empty_scenes)
        assert sb.scenes == []

    def test_scene_discriminator_picks_correct_type(self, valid_storyboard_dict):
        sb = Storyboard(**valid_storyboard_dict)
        assert sb.scenes[0].type == "title"
        assert sb.scenes[1].type == "bullet_list"
        assert sb.scenes[2].type == "closing"

    def test_meta_defaults(self):
        """Meta with only a title should fill in all defaults."""
        sb = Storyboard(
            meta={"title": "Defaults"},
            scenes=[{"type": "closing", "id": "end"}],
        )
        assert sb.meta.author == "Auto-generated"
        assert sb.meta.fps == 60
        assert sb.meta.output_format == "webm"
        assert sb.meta.color_theme == "wong"
