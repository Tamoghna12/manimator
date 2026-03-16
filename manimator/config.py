"""Shared configuration: colors, timing, fonts, spacing, palettes."""

import shutil

# ── Color Palettes ──────────────────────────────────────────────────────────
THEMES = {
    "wong": {
        "bg_main": "#FAFAFA", "bg_card": "#FFFFFF", "bg_alt": "#F5F5F5",
        "bg_dark": "#1a1a2e",
        "blue": "#0173B2", "orange": "#DE8F05", "green": "#029E73",
        "red": "#CC78BC", "purple": "#CA9161", "cyan": "#56B4E9",
        "deep_red": "#D55E00", "yellow": "#F0E442",
        "text_dark": "#1A1A1A", "text_body": "#333333",
        "text_light": "#666666", "text_muted": "#999999",
        "border": "#E0E0E0", "divider": "#CCCCCC", "highlight": "#FFF3CD",
        "palette": [
            "#0173B2", "#DE8F05", "#029E73", "#CC78BC",
            "#CA9161", "#949494", "#56B4E9", "#F0E442",
        ],
    },
    "tol_bright": {
        "bg_main": "#FFFFFF", "bg_card": "#FAFAFA", "bg_alt": "#F5F5F5",
        "bg_dark": "#121212",
        "blue": "#4477AA", "orange": "#CCBB44", "green": "#228833",
        "red": "#EE6677", "purple": "#AA3377", "cyan": "#66CCEE",
        "deep_red": "#EE6677", "yellow": "#CCBB44",
        "text_dark": "#1A1A1A", "text_body": "#333333",
        "text_light": "#666666", "text_muted": "#999999",
        "border": "#E0E0E0", "divider": "#CCCCCC", "highlight": "#FFF9E6",
        "palette": [
            "#4477AA", "#EE6677", "#228833", "#CCBB44",
            "#66CCEE", "#AA3377", "#BBBBBB",
        ],
    },
    "npg": {
        "bg_main": "#FAFAFA", "bg_card": "#FFFFFF", "bg_alt": "#F5F5F5",
        "bg_dark": "#1a1a2e",
        "blue": "#4DBBD5", "orange": "#F39B7F", "green": "#00A087",
        "red": "#E64B35", "purple": "#8491B4", "cyan": "#91D1C2",
        "deep_red": "#E64B35", "yellow": "#B09C85",
        "text_dark": "#1A1A1A", "text_body": "#333333",
        "text_light": "#666666", "text_muted": "#999999",
        "border": "#E0E0E0", "divider": "#CCCCCC", "highlight": "#FFF3CD",
        "palette": [
            "#E64B35", "#4DBBD5", "#00A087", "#3C5488",
            "#F39B7F", "#8491B4", "#91D1C2", "#B09C85",
        ],
    },
}

# Default theme
COLORS = THEMES["wong"]
PALETTE = COLORS["palette"]

TIMING = {
    "title_fade": 1.5,
    "element_fade": 0.5,
    "group_fade": 0.8,
    "scene_pause": 2.0,
    "transition": 0.4,
}

FONTS = {
    "section_header": 36,
    "scene_title": 32,
    "card_title": 26,
    "body_text": 22,
    "stat_value": 42,
    "stat_label": 18,
    "table_header": 20,
    "table_cell": 18,
    "footnote": 16,
}

SPACING = {
    "page_top": 0.6,
    "page_left": 0.8,
    "page_right": 0.6,
    "page_bottom": 0.7,
    "card_pad_x": 0.55,
    "card_title_pad": 0.45,
}

# ── System paths ────────────────────────────────────────────────────────────
FFMPEG_SYSTEM = "/usr/bin/ffmpeg"
FFMPEG_CONDA = shutil.which("ffmpeg")
INTERMEDIATE_FORMAT = ".mp4"


def set_theme(name: str):
    """Switch the active color theme."""
    global COLORS, PALETTE
    COLORS = THEMES[name]
    PALETTE = COLORS["palette"]
