"""Tests for manimator.llm — JSON extraction, provider registry, and storyboard generation."""

import json
from unittest.mock import patch, MagicMock

import pytest

from manimator.llm import extract_json, list_providers, generate_storyboard, PROVIDERS


# ── Test extract_json ────────────────────────────────────────────────────────


class TestExtractJson:
    """Tests for JSON extraction from LLM output."""

    def test_clean_json(self):
        """Clean JSON string parses directly."""
        data = {"meta": {"title": "Test"}, "scenes": []}
        assert extract_json(json.dumps(data)) == data

    def test_markdown_fenced_json(self):
        """JSON inside ```json ... ``` fences is extracted."""
        raw = '```json\n{"meta": {"title": "Fenced"}, "scenes": []}\n```'
        result = extract_json(raw)
        assert result["meta"]["title"] == "Fenced"

    def test_fenced_without_language_tag(self):
        """JSON inside ``` ... ``` fences (no language) is extracted."""
        raw = '```\n{"meta": {"title": "NoLang"}, "scenes": []}\n```'
        result = extract_json(raw)
        assert result["meta"]["title"] == "NoLang"

    def test_leading_trailing_prose(self):
        """JSON surrounded by prose is extracted."""
        raw = (
            "Here is the storyboard:\n\n"
            '{"meta": {"title": "Prose"}, "scenes": []}\n\n'
            "I hope this helps!"
        )
        result = extract_json(raw)
        assert result["meta"]["title"] == "Prose"

    def test_no_json_raises_valueerror(self):
        """Text with no JSON raises ValueError."""
        with pytest.raises(ValueError, match="No JSON object found"):
            extract_json("This is just plain text with no JSON at all.")

    def test_nested_braces(self):
        """Deeply nested JSON with inner braces parses correctly."""
        data = {
            "meta": {"title": "Nested"},
            "scenes": [
                {
                    "type": "bar_chart",
                    "id": "chart",
                    "header": "Data",
                    "bars": [
                        {"label": "A", "value": 80, "color_key": "blue"},
                        {"label": "B", "value": 60, "color_key": "green"},
                    ],
                }
            ],
        }
        raw = f"Sure! Here's the storyboard:\n```json\n{json.dumps(data, indent=2)}\n```"
        result = extract_json(raw)
        assert len(result["scenes"][0]["bars"]) == 2

    def test_json_with_strings_containing_braces(self):
        """JSON containing brace characters inside strings parses correctly."""
        data = {"meta": {"title": "Set {A, B}"}, "scenes": []}
        raw = json.dumps(data)
        assert extract_json(raw)["meta"]["title"] == "Set {A, B}"


# ── Test Provider Registry ───────────────────────────────────────────────────


class TestProviderRegistry:
    """Tests for provider registry structure and list_providers()."""

    def test_all_providers_have_required_keys(self):
        """Every provider entry has models, default, and env_key."""
        for name, info in PROVIDERS.items():
            assert "models" in info, f"{name} missing 'models'"
            assert "default" in info, f"{name} missing 'default'"
            assert "env_key" in info, f"{name} missing 'env_key'"

    def test_list_providers_returns_dict(self):
        """list_providers() returns dict mapping provider names to model lists."""
        result = list_providers()
        assert isinstance(result, dict)
        assert "openai" in result
        assert "anthropic" in result
        assert isinstance(result["openai"], list)

    def test_default_model_in_models_list(self):
        """Each provider's default model appears in its models list (except openai_compatible)."""
        for name, info in PROVIDERS.items():
            if name == "openai_compatible":
                continue
            assert info["default"] in info["models"], (
                f"{name}: default '{info['default']}' not in models {info['models']}"
            )


# ── Test generate_storyboard ─────────────────────────────────────────────────


class TestGenerateStoryboard:
    """Tests for storyboard generation with mocked LLM calls."""

    VALID_STORYBOARD = {
        "meta": {
            "title": "Test Topic",
            "color_theme": "wong",
            "format": "presentation",
            "resolution": [1920, 1080],
        },
        "scenes": [
            {
                "type": "title",
                "id": "intro",
                "title": "Test Topic",
                "subtitle": "An explainer",
            },
            {
                "type": "closing",
                "id": "refs",
                "title": "References",
                "references": ["Author (2024) Journal"],
            },
        ],
    }

    @patch("manimator.llm._call_openai")
    def test_valid_generation(self, mock_call):
        """Valid LLM response produces validated storyboard dict."""
        mock_call.return_value = json.dumps(self.VALID_STORYBOARD)
        result = generate_storyboard(
            topic="Test Topic",
            provider="openai",
            api_key="test-key",
        )
        assert result["meta"]["title"] == "Test Topic"
        assert len(result["scenes"]) == 2
        mock_call.assert_called_once()

    @patch("manimator.llm._call_openai")
    def test_strips_fences(self, mock_call):
        """LLM response with markdown fences is handled correctly."""
        fenced = f"```json\n{json.dumps(self.VALID_STORYBOARD)}\n```"
        mock_call.return_value = fenced
        result = generate_storyboard(
            topic="Test Topic",
            provider="openai",
            api_key="test-key",
        )
        assert result["meta"]["title"] == "Test Topic"

    @patch("manimator.llm._call_openai")
    def test_retries_on_validation_error(self, mock_call):
        """First attempt with invalid schema triggers retry with error feedback."""
        invalid = {"meta": {"title": "Bad"}, "scenes": [{"type": "nonexistent", "id": "x"}]}
        mock_call.side_effect = [
            json.dumps(invalid),
            json.dumps(self.VALID_STORYBOARD),
        ]
        result = generate_storyboard(
            topic="Test Topic",
            provider="openai",
            api_key="test-key",
            max_retries=1,
        )
        assert result["meta"]["title"] == "Test Topic"
        assert mock_call.call_count == 2
        # Second call should include error feedback
        second_prompt = mock_call.call_args_list[1][0][0]
        assert "PREVIOUS ATTEMPT FAILED" in second_prompt

    def test_raises_on_missing_api_key(self):
        """Missing API key raises ValueError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="No API key"):
                generate_storyboard(
                    topic="Test",
                    provider="openai",
                    api_key="",
                )

    def test_raises_on_unknown_provider(self):
        """Unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            generate_storyboard(
                topic="Test",
                provider="nonexistent_provider",
                api_key="key",
            )

    @patch("manimator.llm._call_openai")
    def test_uses_env_key_fallback(self, mock_call):
        """Falls back to environment variable when api_key not provided."""
        mock_call.return_value = json.dumps(self.VALID_STORYBOARD)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            result = generate_storyboard(
                topic="Test",
                provider="openai",
            )
        assert result["meta"]["title"] == "Test Topic"
        # Verify the env key was used
        call_args = mock_call.call_args
        assert call_args[0][2] == "env-key"  # third positional arg is api_key

    @patch("manimator.llm._call_openai")
    def test_uses_default_model(self, mock_call):
        """Default model is used when model is not specified."""
        mock_call.return_value = json.dumps(self.VALID_STORYBOARD)
        generate_storyboard(
            topic="Test",
            provider="openai",
            api_key="key",
        )
        call_args = mock_call.call_args
        assert call_args[0][1] == "gpt-4o-mini"  # second positional arg is model
