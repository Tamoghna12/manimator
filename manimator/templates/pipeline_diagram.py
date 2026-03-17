import numpy as np
from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import (
    create_section_header, make_card, fade_out_all,
    animate_callout, resolve_color,
)

# ── Design tokens ──────────────────────────────────────────────────────────
SCI_PALETTE = [
    "#4477AA", "#EE6677", "#228833",
    "#CCBB44", "#AA3377", "#EE8866",
]
TRACK_W      = 4.2
TRACK_H      = 3.8
CENTER_W     = 4.6
CENTER_H     = 5.8
ARROW_SW     = 2.8
PULSE_COLOR  = WHITE


# ── Helpers ────────────────────────────────────────────────────────────────

def _resolve(key: str, fallback_idx: int = 0) -> str:
    try:
        return resolve_color(key)
    except Exception:
        return SCI_PALETTE[fallback_idx % len(SCI_PALETTE)]


def _title_strip(width: float, label: str, sublabel: str,
                 color: str) -> VGroup:
    """Coloured header strip with title + optional sublabel."""
    bar = Rectangle(
        width=width - 0.04, height=0.54,
        fill_color=color, fill_opacity=0.20, stroke_width=0,
    )
    title_mob = Text(label, font_size=17, color=color, weight=BOLD)
    if title_mob.width > bar.width - 0.25:
        title_mob.scale_to_fit_width(bar.width - 0.25)
    title_mob.move_to(bar)

    strip = VGroup(bar, title_mob)
    if sublabel:
        sub = Text(sublabel, font_size=12, color=COLORS["text_muted"])
        sub.next_to(bar, DOWN, buff=0.08)
        strip.add(sub)
    return strip


def _item_row(item: dict | str, color: str) -> VGroup:
    """
    Structured item row. Accepts str or:
      { "text": "...", "tag": "→ output", "highlight": True }
    """
    if isinstance(item, str):
        item = {"text": item}

    icon = Text("▸", font_size=13, color=color)
    body = MarkupText(item["text"], font_size=13, color=COLORS["text_body"])

    row = VGroup(icon, body).arrange(RIGHT, buff=0.15, aligned_edge=UP)

    if item.get("tag"):
        tag_bg = RoundedRectangle(
            corner_radius=0.06, height=0.22,
            fill_color=color, fill_opacity=0.20,
            stroke_color=color, stroke_width=0.6,
        )
        tag_lbl = Text(item["tag"], font_size=11, color=color)
        tag_bg.width = tag_lbl.width + 0.18
        tag_lbl.move_to(tag_bg)
        row = VGroup(row, VGroup(tag_bg, tag_lbl)).arrange(
            RIGHT, buff=0.18, aligned_edge=UP)

    if item.get("highlight"):
        bg = Rectangle(
            width=row.width + 0.18, height=row.height + 0.10,
            fill_color=color, fill_opacity=0.12, stroke_width=0,
        ).move_to(row)
        return VGroup(bg, row)
    return VGroup(row)


def _build_track_card(track_data: dict, w: float, h: float,
                      fallback_idx: int) -> tuple[VGroup, VGroup]:
    """Returns (full_card VGroup, items VGroup)."""
    col = _resolve(track_data.get("color_key", ""), fallback_idx)
    card = make_card(w, h, stroke_color=col, stroke_width=2.2)

    strip = _title_strip(w, track_data["label"],
                         track_data.get("sublabel", ""), col)
    strip.move_to(card.get_top() + DOWN * (strip.height / 2 + 0.02))

    sep = Line(
        card.get_left() + RIGHT * 0.12,
        card.get_right() + LEFT * 0.12,
        stroke_width=0.7, color=col, stroke_opacity=0.35,
    ).next_to(strip, DOWN, buff=0.0)

    items = VGroup(*[_item_row(it, col)
                     for it in track_data.get("items", [])])
    items.arrange(DOWN, buff=0.22, aligned_edge=LEFT)

    avail_h = h - strip.height - 0.5
    if items.height > avail_h:
        items.scale_to_fit_height(avail_h)

    items.next_to(sep, DOWN, buff=0.2)
    items.align_to(card.get_left() + RIGHT * 0.22, LEFT)

    return VGroup(card, strip, sep, items), items


def _build_center_card(cb: dict, w: float, h: float) -> tuple[VGroup, VGroup, list]:
    """
    Center card supports:
      cb["sections"]: [{"label": "Input", "items": [...], "color_key": "..."}]
    Falls back to flat cb["items"] list.
    """
    col = _resolve(cb.get("color_key", ""), 3)
    card = make_card(w, h, stroke_color=col, stroke_width=2.8)

    strip = _title_strip(w, cb["label"], cb.get("sublabel", ""), col)
    strip.move_to(card.get_top() + DOWN * (strip.height / 2 + 0.02))

    sep = Line(
        card.get_left() + RIGHT * 0.12,
        card.get_right() + LEFT * 0.12,
        stroke_width=0.9, color=col, stroke_opacity=0.40,
    ).next_to(strip, DOWN, buff=0.0)

    section_groups = []

    if "sections" in cb:
        body = VGroup()
        for si, sec in enumerate(cb["sections"]):
            s_col = _resolve(sec.get("color_key", ""), si)
            sec_label = Text(sec["label"], font_size=13,
                             color=s_col, weight=BOLD)
            sec_items = VGroup(*[_item_row(it, s_col)
                                  for it in sec.get("items", [])])
            sec_items.arrange(DOWN, buff=0.16, aligned_edge=LEFT)
            sec_block = VGroup(sec_label, sec_items)
            sec_block.arrange(DOWN, buff=0.10, aligned_edge=LEFT)
            body.add(sec_block)
            section_groups.append(sec_block)

        body.arrange(DOWN, buff=0.28, aligned_edge=LEFT)

    else:
        flat = VGroup(*[_item_row(it, col) for it in cb.get("items", [])])
        flat.arrange(DOWN, buff=0.22, aligned_edge=LEFT)
        body = flat
        section_groups = [body]

    avail_h = h - strip.height - 0.45
    if body.height > avail_h:
        body.scale_to_fit_height(avail_h)

    body.next_to(sep, DOWN, buff=0.22)
    body.align_to(card.get_left() + RIGHT * 0.24, LEFT)

    return VGroup(card, strip, sep, body), body, section_groups


def _smart_arrow(
    start: np.ndarray, end: np.ndarray,
    color: str,
    label: str = "",
    direction: str = "right",   # "right" | "left" | "both"
    curved: bool = False,
    angle: float = 0.4,
) -> tuple[VMobject, VMobject | None]:
    """
    Creates a directional or double arrow with an optional floating label.
    Returns (arrow, label_mob or None).
    """
    kw = dict(color=color, stroke_width=ARROW_SW, buff=0.12,
              max_tip_length_to_length_ratio=0.10)

    if curved:
        if direction == "both":
            arr = CurvedDoubleArrow(start, end, angle=angle, **kw)
        else:
            arr = CurvedArrow(start, end, angle=angle, **kw)
            if direction == "left":
                arr = CurvedArrow(end, start, angle=angle, **kw)
    else:
        if direction == "both":
            arr = DoubleArrow(start, end, **kw)
        elif direction == "left":
            arr = Arrow(end, start, **kw)
        else:
            arr = Arrow(start, end, **kw)

    lbl_mob = None
    if label:
        mid   = (start + end) / 2
        perp  = UP * 0.28 if not curved else UP * 0.45
        lbl_mob = MarkupText(
            f'<i>{label}</i>', font_size=12, color=color
        ).move_to(mid + perp)

    return arr, lbl_mob


def _pulse_along_arrow(scene: Scene, arrow: VMobject, color: str = PULSE_COLOR):
    """Animate a dot travelling along the arrow path (data-flow metaphor)."""
    pulse = Dot(radius=0.07, color=color, fill_opacity=0.9)
    pulse.move_to(arrow.get_start())
    scene.play(
        MoveAlongPath(pulse, arrow, rate_func=linear),
        run_time=0.45,
    )
    scene.play(FadeOut(pulse, scale=1.8), run_time=0.15)


# ── Main render ────────────────────────────────────────────────────────────

def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    lt_data = data["left_track"]
    rt_data = data["right_track"]
    cb_data = data["center_block"]

    # ── Build cards ────────────────────────────────────────────────────
    left_card,   left_items   = _build_track_card(lt_data, TRACK_W, TRACK_H, 0)
    right_card,  right_items  = _build_track_card(rt_data, TRACK_W, TRACK_H, 1)
    center_card, center_body, center_sections = _build_center_card(
        cb_data, CENTER_W, CENTER_H)

    # ── Positioning ───────────────────────────────────────────────────
    gap       = 0.55
    cx_offset = (CENTER_W + TRACK_W) / 2 + gap
    center_card.move_to(ORIGIN + DOWN * 0.4)
    left_card.move_to( LEFT  * cx_offset + DOWN * 0.4)
    right_card.move_to(RIGHT * cx_offset + DOWN * 0.4)

    lt_col = _resolve(lt_data.get("color_key", ""), 0)
    rt_col = _resolve(rt_data.get("color_key", ""), 1)

    # ── Arrows ────────────────────────────────────────────────────────
    l_dir   = lt_data.get("arrow_direction", "right")
    r_dir   = rt_data.get("arrow_direction", "left")
    l_label = lt_data.get("arrow_label", "")
    r_label = rt_data.get("arrow_label", "")
    curved  = data.get("curved_arrows", False)

    arrow_l, lbl_l = _smart_arrow(
        left_card.get_right(), center_card.get_left(),
        lt_col, l_label, l_dir, curved,
    )
    arrow_r, lbl_r = _smart_arrow(
        center_card.get_right(), right_card.get_left(),
        rt_col, r_label, r_dir, curved,
    )

    # ── Optional top connection arc ────────────────────────────────────
    arc_conn = VMobject()
    if data.get("top_arc"):
        arc_conn = CurvedDoubleArrow(
            left_card.get_top() + UP * 0.05,
            right_card.get_top() + UP * 0.05,
            angle=-0.55,
            color=COLORS["text_muted"],
            stroke_width=1.5,
        )

    mobs = [header, left_card, right_card, center_card,
            arrow_l, arrow_r, arc_conn]
    if lbl_l: mobs.append(lbl_l)
    if lbl_r: mobs.append(lbl_r)

    # ── Animation sequence ─────────────────────────────────────────────

    # 1. Tracks fly in from edges
    left_card.shift( LEFT  * (config.frame_width / 2 + TRACK_W))
    right_card.shift(RIGHT * (config.frame_width / 2 + TRACK_W))
    scene.play(
        left_card.animate.shift( RIGHT * (config.frame_width / 2 + TRACK_W)),
        right_card.animate.shift(LEFT  * (config.frame_width / 2 + TRACK_W)),
        rate_func=rush_from, run_time=0.55,
    )

    # 2. Track items stagger in
    all_rows = list(left_items) + list(right_items)
    scene.play(
        LaggedStart(*[FadeIn(r, shift=RIGHT * 0.10) for r in all_rows],
                    lag_ratio=0.08),
        run_time=max(0.5, len(all_rows) * 0.09),
    )

    # 3. Center card grows from centre
    scene.play(GrowFromCenter(center_card[0]), run_time=0.35)
    scene.play(FadeIn(center_card[1]), FadeIn(center_card[2]), run_time=0.25)

    # 4. Center sections reveal sequentially
    for sg in center_sections:
        scene.play(
            LaggedStart(*[FadeIn(item, shift=DOWN * 0.08) for item in sg],
                        lag_ratio=0.12),
            run_time=max(0.35, len(sg) * 0.10),
        )

    # 5. Arrows draw
    arrow_anims = [GrowArrow(arrow_l), GrowArrow(arrow_r)]
    if arc_conn.points.size > 0:
        arrow_anims.append(Create(arc_conn))
    scene.play(*arrow_anims, run_time=0.5)

    if lbl_l: scene.play(FadeIn(lbl_l), run_time=0.2)
    if lbl_r: scene.play(FadeIn(lbl_r), run_time=0.2)

    # 6. Data-flow pulse (optional — one pulse per arrow)
    if data.get("show_pulse", True):
        _pulse_along_arrow(scene, arrow_l, lt_col)
        _pulse_along_arrow(scene, arrow_r, rt_col)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)

