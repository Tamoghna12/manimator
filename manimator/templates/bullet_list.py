from __future__ import annotations
from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import (
    create_section_header, make_card,
    fade_out_all, animate_callout,
)

# ── Design tokens ──────────────────────────────────────────────────────────
SCI_PALETTE   = ["#4477AA","#EE6677","#228833","#CCBB44","#AA3377","#EE8866","#44BB99"]
BODY_FS       = 19
SUB_FS        = 16
TAG_FS        = 12
MAX_BODY_W    = 13.0    # scene units before scaling
TWO_COL_THRESH = 7      # switch to two columns beyond this many top-level items
DIM_OPACITY   = 0.28    # opacity of "read" bullets when focus mode is active


# ── Bullet row builder ─────────────────────────────────────────────────────

def _tag_pill(text: str, color: str) -> VGroup:
    bg = RoundedRectangle(
        corner_radius=0.07, height=0.26,
        fill_color=color, fill_opacity=0.22,
        stroke_color=color, stroke_width=0.7,
    )
    lbl = Text(text, font_size=TAG_FS, color=color, weight=BOLD)
    bg.width = lbl.width + 0.22
    lbl.move_to(bg)
    return VGroup(bg, lbl)


def _build_row(
    item:      dict | str,
    accent:    str,
    numbered:  bool,
    index:     int,
    max_width: float,
) -> VGroup:
    """
    Accepts str (legacy) or dict:
      {
        "text":      "MarkupText body — supports <b>, <i>, <sup>",
        "icon":      "✔",          # overrides default bullet / number
        "tag":       "NEW",         # small pill badge on the right
        "highlight": True,          # semi-transparent accent bg strip
        "sub":       ["sub-item 1", "sub-item 2"],   # indented children
        "color":     "#EE6677",     # per-item accent override
      }
    """
    if isinstance(item, str):
        item = {"text": item}

    item_color = item.get("color", accent)

    # ── Bullet / number glyph ─────────────────────────────────────────
    if item.get("icon"):
        glyph = Text(item["icon"], font_size=BODY_FS, color=item_color)
    elif numbered:
        glyph = Text(f"{index + 1}.", font_size=BODY_FS,
                     color=item_color, weight=BOLD)
    else:
        glyph = Text("▸", font_size=BODY_FS, color=item_color)

    # ── Body text ─────────────────────────────────────────────────────
    body = MarkupText(item["text"], font_size=BODY_FS,
                      color=COLORS["text_body"])
    if body.width > max_width - glyph.width - 0.6:
        body.scale_to_fit_width(max_width - glyph.width - 0.6)

    row_inner = VGroup(glyph, body).arrange(RIGHT, buff=0.20, aligned_edge=UP)

    # ── Optional tag pill ─────────────────────────────────────────────
    if item.get("tag"):
        pill = _tag_pill(item["tag"], item_color)
        row_inner = VGroup(row_inner, pill).arrange(RIGHT, buff=0.22,
                                                     aligned_edge=UP)

    # ── Optional highlight strip ──────────────────────────────────────
    if item.get("highlight"):
        bg_strip = Rectangle(
            width=max_width + 0.12,
            height=row_inner.height + 0.12,
            fill_color=item_color, fill_opacity=0.13,
            stroke_width=0,
        ).move_to(row_inner)
        row_inner = VGroup(bg_strip, row_inner)

    # ── Optional sub-bullets ──────────────────────────────────────────
    sub_group = VGroup()
    for sub in item.get("sub", []):
        sub_text = MarkupText(
            f'<span foreground="{COLORS["text_muted"]}">╰  </span>' +
            (sub if isinstance(sub, str) else sub.get("text", "")),
            font_size=SUB_FS,
            color=COLORS["text_muted"],
        )
        if sub_text.width > max_width - 0.8:
            sub_text.scale_to_fit_width(max_width - 0.8)
        sub_group.add(sub_text)

    if len(sub_group):
        sub_group.arrange(DOWN, buff=0.10, aligned_edge=LEFT)
        full_row = VGroup(row_inner, sub_group)
        full_row.arrange(DOWN, buff=0.12, aligned_edge=LEFT)
        # Indent sub-bullets
        sub_group.shift(RIGHT * 0.45)
        return full_row

    return VGroup(row_inner)


def _progress_bar(
    total: int, current: int, color: str, width: float = 13.0
) -> VGroup:
    """Thin progress bar showing slide position within the section."""
    track = Rectangle(width=width, height=0.07,
                      fill_color=COLORS["text_muted"], fill_opacity=0.22,
                      stroke_width=0)
    fill  = Rectangle(width=width * (current / max(total, 1)), height=0.07,
                      fill_color=color, fill_opacity=0.75,
                      stroke_width=0)
    fill.align_to(track, LEFT)
    return VGroup(track, fill)


def _section_label(text: str, color: str, width: float) -> VGroup:
    """Optional section divider between logical groups."""
    lbl  = Text(text, font_size=13, color=color, weight=BOLD)
    rule = Line(
        lbl.get_right() + RIGHT * 0.18,
        RIGHT * (width / 2),
        stroke_width=0.7, color=color, stroke_opacity=0.40,
    )
    return VGroup(lbl, rule).arrange(RIGHT, buff=0.15, aligned_edge=UP)


# ── Main render ────────────────────────────────────────────────────────────

def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    items        = data["items"]
    numbered     = data.get("numbered", False)
    focus_mode   = data.get("focus_mode", False)   # dim previous bullets
    accent       = data.get("accent_color", SCI_PALETTE[0])
    section_idx  = data.get("section_index")       # (current, total) for progress bar
    sections     = data.get("sections", [])        # optional section dividers:
                                                    #   [{"after": 2, "label": "Theory"}]
    max_w = MAX_BODY_W

    # Resolve accent
    try:
        from manimator.helpers import resolve_color
        accent = resolve_color(accent)
    except Exception:
        pass

    # ── Two-column layout threshold ────────────────────────────────────
    top_level = [it for it in items if isinstance(it, dict) and "sub" not in it
                 or isinstance(it, str)]
    two_col = len(items) > TWO_COL_THRESH

    if two_col:
        max_w = 5.8
        half  = len(items) // 2
        left_items  = items[:half]
        right_items = items[half:]
    else:
        left_items  = items
        right_items = []

    # ── Card background ────────────────────────────────────────────────
    card_h = 6.2
    card_w = 15.5 if two_col else 14.5
    bg = make_card(card_w, card_h, stroke_color=accent)

    # ── Title strip inside card ────────────────────────────────────────
    raw_header = (data["header"].split(". ", 1)[-1]
                  if ". " in data["header"] else data["header"])
    strip_bar = Rectangle(
        width=card_w - 0.04, height=0.50,
        fill_color=accent, fill_opacity=0.18, stroke_width=0,
    )
    strip_lbl = Text(raw_header, font_size=FONTS["card_title"],
                     color=accent, weight=BOLD)
    if strip_lbl.width > strip_bar.width - 0.3:
        strip_lbl.scale_to_fit_width(strip_bar.width - 0.3)
    strip_lbl.move_to(strip_bar)
    strip = VGroup(strip_bar, strip_lbl)

    sep = Line(
        bg.get_left()  + RIGHT * 0.15,
        bg.get_right() + LEFT  * 0.15,
        stroke_width=0.7, color=accent, stroke_opacity=0.35,
    )

    # Position card below header
    bg.next_to(header, DOWN, buff=0.40)
    strip.move_to(bg.get_top() + DOWN * (strip.height / 2 + 0.02))
    sep.next_to(strip, DOWN, buff=0.0)

    # ── Progress bar (optional) ────────────────────────────────────────
    prog_mob = VMobject()
    if section_idx:
        cur, tot = section_idx
        prog_mob = _progress_bar(tot, cur, accent, width=card_w - 0.4)
        prog_mob.move_to(bg.get_bottom() + UP * 0.22)

    mobs = [header, bg, strip, sep, prog_mob]

    scene.play(
        Create(bg), FadeIn(strip), Create(sep),
        run_time=TIMING.get("group_fade", 0.45),
    )
    if section_idx:
        scene.play(FadeIn(prog_mob), run_time=0.25)

    # ── Build and animate rows ─────────────────────────────────────────

    def _animate_column(
        col_items: list,
        anchor_left: float,
        anchor_top: float,
        col_max_w: float,
    ) -> list[VGroup]:
        """Place and animate one column of bullets. Returns list of row VGroups."""
        rows: list[VGroup] = []
        cursor_y = anchor_top

        for i, item in enumerate(col_items):
            # Section divider injection
            for sec in sections:
                if sec.get("after") == i - 1:
                    div = _section_label(sec["label"], accent, col_max_w)
                    div.move_to([anchor_left + div.width / 2, cursor_y, 0],
                                 aligned_edge=LEFT)
                    cursor_y -= div.height + 0.16
                    scene.play(FadeIn(div, shift=RIGHT * 0.08), run_time=0.18)
                    mobs.append(div)

            row = _build_row(item, accent, numbered, i, col_max_w)
            row.move_to([anchor_left, cursor_y, 0], aligned_edge=LEFT + UP)
            cursor_y -= row.height + 0.28

            # Focus mode: dim all previous rows before revealing new one
            if focus_mode and rows:
                scene.play(
                    *[r.animate.set_opacity(DIM_OPACITY) for r in rows],
                    run_time=0.15,
                )

            scene.play(FadeIn(row, shift=RIGHT * 0.14), run_time=0.22)
            rows.append(row)
            mobs.append(row)

        return rows

    # ── Column anchors ─────────────────────────────────────────────────
    top_y    = sep.get_bottom()[1] - 0.28
    left_x   = bg.get_left()[0] + 0.32

    if two_col:
        mid_x = bg.get_center()[0]
        _animate_column(left_items,  left_x,         top_y, max_w)
        _animate_column(right_items, mid_x + 0.15,   top_y, max_w)
        # Vertical divider between columns
        col_div = Line(
            [mid_x, sep.get_bottom()[1] - 0.12, 0],
            [mid_x, bg.get_bottom()[1]  + 0.30, 0],
            stroke_width=0.7, color=accent, stroke_opacity=0.25,
        )
        scene.play(Create(col_div), run_time=0.2)
        mobs.append(col_div)
    else:
        _animate_column(left_items, left_x, top_y, max_w)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)

