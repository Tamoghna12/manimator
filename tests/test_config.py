"""Tests for manimator.config — color themes and configuration constants."""

from manimator.config import THEMES


class TestThemes:
    """Verify THEMES dict has expected keys and required color entries."""

    EXPECTED_THEMES = ("wong", "npg", "tol_bright")

    REQUIRED_COLOR_KEYS = (
        "bg_main", "bg_card", "bg_alt", "bg_dark",
        "blue", "orange", "green", "red", "purple", "cyan",
        "text_dark", "text_body", "text_light", "text_muted",
        "border", "divider", "highlight", "palette",
    )

    def test_themes_contains_expected_keys(self):
        for name in self.EXPECTED_THEMES:
            assert name in THEMES, f"Missing theme: {name!r}"

    def test_each_theme_has_required_color_keys(self):
        for name in self.EXPECTED_THEMES:
            theme = THEMES[name]
            for key in self.REQUIRED_COLOR_KEYS:
                assert key in theme, (
                    f"Theme {name!r} missing key {key!r}"
                )

    def test_palette_is_non_empty_list(self):
        for name in self.EXPECTED_THEMES:
            palette = THEMES[name]["palette"]
            assert isinstance(palette, list)
            assert len(palette) >= 1

    def test_color_values_are_hex_strings(self):
        for name in self.EXPECTED_THEMES:
            theme = THEMES[name]
            for key in ("blue", "orange", "green", "red"):
                val = theme[key]
                assert isinstance(val, str)
                assert val.startswith("#"), (
                    f"Theme {name!r} key {key!r} = {val!r} is not a hex color"
                )
