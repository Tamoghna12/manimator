from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import (
    create_section_header, make_card, fade_out_all, animate_callout,
)

# ── Design tokens ──────────────────────────────────────────────────────────
PANEL_W      = 6.8
PANEL_H      = 5.6
PANEL_GAP    = 1.1      # gap between the two panels (houses VS badge)
TITLE_PAD    = 0.42     # distance from card top to title text
BULLET_ICON  = "▸"      # default bullet prefix
HIGHLIGHT_OP = 0.18     # fill opacity for highlighted rows


def _panel_title_bar(width: float, label: str, color: str) -> VGroup:
    """
    Coloured top-strip header for a card — more structural than plain text.
    Returns VGroup(bar, text) with bar flush to the card top.
    """
    bar = Rectangle(
        width=width - 0.04,   # slight inset so corners don't overdraw border
        height=0.52,
        fill_color=color,
        fill_opacity=0.22,
        stroke_width=0,
    )
    label_mob = Text(label, font_size=FONTS["card_title"],
                     color=color, weight=BOLD)
    # Keep label from overflowing bar width
    if label_mob.width > bar.width - 0.3:
        label_mob.scale_to_fit_width(bar.width - 0.3)
    label_mob.move_to(bar)
    return VGroup(bar, label_mob)


def _bullet_row(item: dict | str, accent: str, font_size: int,
                max_width: float) -> VGroup:
    """
    Accepts a plain string or a structured dict:
      { "text": "...", "icon": "✔", "highlight": True, "tag": "NEW" }
    Returns a VGroup(optional_highlight_bg, icon, text, optional_tag).
    """
    if isinstance(item, str):
        item = {"text": item}

    icon_char = item.get("icon", BULLET_ICON)
    text_str  = item.get("text", "")
    highlight = item.get("highlight", False)
    tag_str   = item.get("tag", "")

    icon = Text(icon_char, font_size=font_size, color=accent)
    body = MarkupText(text_str, font_size=font_size, color=COLORS["text_body"])

    # Overflow guard: scale body if too wide for the panel
    if body.width > max_width - icon.width - 0.4:
        body.scale_to_fit_width(max_width - icon.width - 0.4)

    row_content = VGroup(icon, body).arrange(RIGHT, buff=0.18, aligned_edge=UP)

    # Optional tag pill (e.g. "NEW", "p<0.05")
    if tag_str:
        tag_bg = RoundedRectangle(
            corner_radius=0.07, height=0.26,
            fill_color=accent, fill_opacity=0.25,
            stroke_color=accent, stroke_width=0.7,
        )
        tag_label = Text(tag_str, font_size=font_size - 4,
                         color=accent, weight=BOLD)
        tag_bg.width = tag_label.width + 0.22
        tag_label.move_to(tag_bg)
        tag_pill = VGroup(tag_bg, tag_label)
        row_content = VGroup(row_content, tag_pill).arrange(RIGHT, buff=0.2,
                                                            aligned_edge=UP)

    # Optional highlight strip behind the row
    if highlight:
        bg = Rectangle(
            width=max_width + 0.1,
            height=row_content.height + 0.12,
            fill_color=accent,
            fill_opacity=HIGHLIGHT_OP,
            stroke_width=0,
        ).move_to(row_content)
        return VGroup(bg, row_content)

    return VGroup(row_content)


def _build_panel(title: str, items: list, color: str,
                 card: VMobject) -> tuple[VGroup, VGroup]:
    """
    Returns (full_panel VGroup, bullets VGroup).
    Bullets are returned separately so they can be animated independently.
    """
    w = card.width
    h = card.height

    title_bar = _panel_title_bar(w, title, color)
    # Flush to card top interior edge
    title_bar.move_to(card.get_top() + DOWN * (title_bar.height / 2 + 0.02))

    # Separator rule under title bar
    sep = Line(
        card.get_left() + RIGHT * 0.15,
        card.get_right() + LEFT * 0.15,
        stroke_width=0.8,
        color=color,
        stroke_opacity=0.4,
    ).next_to(title_bar, DOWN, buff=0.0)

    max_bw = w - 0.5   # max bullet width in scene units
    bullets = VGroup(*[
        _bullet_row(it, color, FONTS["body_text"], max_bw) for it in items
    ])
    bullets.arrange(DOWN, buff=0.28, aligned_edge=LEFT)

    # Constrain bullet block to fit inside card below title bar
    available_h = h - title_bar.height - 0.55
    if bullets.height > available_h:
        bullets.scale_to_fit_height(available_h)

    # Left-align bullets inside card
    bullets.next_to(sep, DOWN, buff=0.28)
    bullets.align_to(card.get_left() + RIGHT * 0.28, LEFT)

    panel = VGroup(card, title_bar, sep, bullets)
    return panel, bullets


def _vs_badge() -> VGroup:
    """Central VS divider badge."""
    circle = Circle(radius=0.36, fill_color=COLORS.get("surface_alt", "#1E1E2E"),
                    fill_opacity=1.0, stroke_color=COLORS["text_muted"],
                    stroke_width=1.2)
    label  = Text("VS", font_size=18, color=COLORS["text_muted"], weight=BOLD)
    top_tick = Line(UP * 0.36, UP * 1.2, stroke_width=0.8,
                    color=COLORS["text_muted"], stroke_opacity=0.4)
    bot_tick = Line(DOWN * 0.36, DOWN * 1.2, stroke_width=0.8,
                    color=COLORS["text_muted"], stroke_opacity=0.4)
    return VGroup(top_tick, bot_tick, circle, label)


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    # ── Cards ─────────────────────────────────────────────────────────────
    left_card  = make_card(PANEL_W, PANEL_H, stroke_color=COLORS["blue"])
    right_card = make_card(PANEL_W, PANEL_H, stroke_color=COLORS["green"])

    # Position symmetrically with gap for VS badge
    offset = PANEL_W / 2 + PANEL_GAP / 2
    left_card.move_to( LEFT  * offset + DOWN * 0.4)
    right_card.move_to(RIGHT * offset + DOWN * 0.4)

    left_panel,  left_bullets  = _build_panel(
        data["left_title"],  data["left_items"],  COLORS["blue"],  left_card)
    right_panel, right_bullets = _build_panel(
        data["right_title"], data["right_items"], COLORS["green"], right_card)

    vs = _vs_badge().move_to(DOWN * 0.4)

    mobs = [header, left_panel, right_panel, vs]

    # ── Animation ─────────────────────────────────────────────────────────
    # 1. Panels fly in from opposite edges simultaneously
    left_panel.shift( LEFT  * (config.frame_width / 2 + PANEL_W))
    right_panel.shift(RIGHT * (config.frame_width / 2 + PANEL_W))

    scene.play(
        left_panel.animate.shift( RIGHT * (config.frame_width / 2 + PANEL_W)),
        right_panel.animate.shift(LEFT  * (config.frame_width / 2 + PANEL_W)),
        run_time=0.55,
        rate_func=rush_from,
    )

    # 2. VS badge scales in after panels settle
    scene.play(GrowFromCenter(vs, rate_func=overshoot), run_time=0.3)

    # 3. Bullets interleaved L/R — more engaging than sequential [web:50]
    max_rows = max(len(left_bullets), len(right_bullets))
    for i in range(max_rows):
        anims = []
        if i < len(left_bullets):
            anims.append(FadeIn(left_bullets[i],  shift=RIGHT * 0.12))
        if i < len(right_bullets):
            anims.append(FadeIn(right_bullets[i], shift=LEFT  * 0.12))
        if anims:
            scene.play(*anims, run_time=0.22)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)

