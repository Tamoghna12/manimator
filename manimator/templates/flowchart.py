from __future__ import annotations
import numpy as np
from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING, PALETTE
from manimator.helpers import (
    create_section_header, fade_out_all,
    animate_callout, resolve_color,
)

# ── Design tokens ──────────────────────────────────────────────────────────
SCI_PALETTE   = [
    "#4477AA", "#EE6677", "#228833",
    "#CCBB44", "#AA3377", "#EE8866", "#44BB99",
]
BOX_H         = 1.55
GAP           = 0.28
MAX_ROW_W     = 15.5   # scene units; wraps to 2 rows beyond this
BADGE_R       = 0.22   # step-number circle radius
PULSE_COLOR   = WHITE
RECYCLE_COLOR = "#AA3377"


# ── Helpers ────────────────────────────────────────────────────────────────

def _resolve(key: str, idx: int = 0) -> str:
    try:
        return resolve_color(key)
    except Exception:
        return SCI_PALETTE[idx % len(SCI_PALETTE)]


def _stage_card(
    stage: dict,
    idx: int,
    box_w: float,
) -> tuple[VGroup, RoundedRectangle]:
    """
    Builds one flowchart stage card.
    Returns (full VGroup, bare rectangle) — rect kept for arrow anchoring.
    Accepts:
      stage["label"]    : str  — main label (newline splits to two lines)
      stage["sublabel"] : str  — smaller annotation below label (optional)
      stage["color_key"]: str
      stage["bg"]       : str  — fill hex (optional, derived from accent if absent)
      stage["icon"]     : str  — Unicode glyph prepended to label (optional)
    """
    col    = _resolve(stage.get("color_key", ""), idx)
    bg_col = stage.get("bg", col)

    rect = RoundedRectangle(
        width=box_w, height=BOX_H, corner_radius=0.14,
        fill_color=bg_col, fill_opacity=0.18,
        stroke_color=col, stroke_width=2.4,
    )

    # ── Step-number badge ─────────────────────────────────────────────
    badge_circle = Circle(
        radius=BADGE_R,
        fill_color=col, fill_opacity=0.9,
        stroke_width=0,
    ).move_to(rect.get_corner(UL) + RIGHT * BADGE_R + DOWN * BADGE_R)
    badge_num = Text(
        str(idx + 1), font_size=12, color=WHITE, weight=BOLD,
    ).move_to(badge_circle)

    # ── Main label ────────────────────────────────────────────────────
    icon_str  = stage.get("icon", "")
    raw_label = stage["label"].replace("\\n", "\n")
    label_str = f"{icon_str}  {raw_label}" if icon_str else raw_label

    label = Text(
        label_str, font_size=15, color=col, weight=BOLD,
        line_spacing=1.1,
    )
    if label.width > box_w - 0.3:
        label.scale_to_fit_width(box_w - 0.3)

    # ── Sublabel ──────────────────────────────────────────────────────
    sublabel_str = stage.get("sublabel", "")
    content = VGroup(label)
    if sublabel_str:
        sub = MarkupText(
            f'<i>{sublabel_str}</i>', font_size=12,
            color=COLORS["text_muted"],
        )
        if sub.width > box_w - 0.3:
            sub.scale_to_fit_width(box_w - 0.3)
        content.add(sub)
        content.arrange(DOWN, buff=0.12)

    content.move_to(rect.get_center())

    # ── Separator rule under label if sublabel present ────────────────
    parts = VGroup(rect, badge_circle, badge_num, content)
    if sublabel_str:
        sep = Line(
            rect.get_left()  + RIGHT * 0.18,
            rect.get_right() + LEFT  * 0.18,
            stroke_width=0.6, color=col, stroke_opacity=0.3,
        ).next_to(label, DOWN, buff=0.08)
        parts.add(sep)

    return parts, rect


def _connector_arrow(
    start: np.ndarray,
    end:   np.ndarray,
    color: str,
    label_str: str = "",
    vertical: bool = False,
) -> VGroup:
    """Straight arrow with optional floating label."""
    arr = Arrow(
        start, end,
        color=color, stroke_width=2.4, buff=0.10,
        max_tip_length_to_length_ratio=0.18,
    )
    group = VGroup(arr)
    if label_str:
        mid   = (start + end) / 2
        perp  = LEFT * 0.3 if vertical else UP * 0.28
        lbl   = MarkupText(
            f'<i>{label_str}</i>', font_size=11,
            color=color,
        ).move_to(mid + perp)
        group.add(lbl)
    return group


def _pulse(scene: Scene, arrow: VMobject, color: str = PULSE_COLOR):
    """Dot travelling along an arrow — communicates data flow direction."""
    dot = Dot(radius=0.075, color=color, fill_opacity=0.95)
    dot.move_to(arrow.get_start())
    scene.play(
        MoveAlongPath(dot, arrow, rate_func=linear),
        run_time=0.38,
    )
    scene.play(FadeOut(dot, scale=1.6), run_time=0.12)


def _spotlight(scene: Scene, card: VGroup, col: str):
    """Indicate + colour flash on the active stage."""
    scene.play(
        Indicate(card, color=col, scale_factor=1.06),
        run_time=0.4,
    )


def _recycle_arc(
    stage_cards: list[VGroup],
    from_idx: int,
    to_idx: int,
    label_str: str,
    vertical: bool,
    rects: list[RoundedRectangle],
) -> tuple[VMobject, VMobject]:
    """
    Curved recycle arrow looping from stage[from_idx] back to stage[to_idx].
    Routes below the row for horizontal layouts, left for vertical.
    """
    if vertical:
        start = rects[from_idx].get_left()  + LEFT  * 0.08
        end   = rects[to_idx  ].get_left()  + LEFT  * 0.08
        arc   = CurvedArrow(start, end, angle=PI / 2.5,
                             color=RECYCLE_COLOR, stroke_width=2.0)
    else:
        start = rects[from_idx].get_bottom() + DOWN * 0.10
        end   = rects[to_idx  ].get_bottom() + DOWN * 0.10
        arc   = CurvedArrow(start, end, angle=-PI / 2.8,
                             color=RECYCLE_COLOR, stroke_width=2.0)

    lbl = MarkupText(
        f'<i>{label_str}</i>', font_size=12, color=RECYCLE_COLOR,
    )
    lbl.next_to(arc, DOWN if not vertical else LEFT, buff=0.10)
    return arc, lbl


# ── Layout engine ─────────────────────────────────────────────────────────

def _layout(
    stage_cards: list[VGroup],
    rects:       list[RoundedRectangle],
    n:           int,
    box_w:       float,
) -> tuple[VGroup, bool]:
    """
    Places cards and returns (full VGroup, is_vertical).
    Wraps to 2 rows if too wide; falls back to vertical column if > 2 rows needed.
    """
    total_w = n * box_w + (n - 1) * GAP
    vertical = total_w > MAX_ROW_W * 1.35

    if vertical:
        group = VGroup(*stage_cards)
        group.arrange(DOWN, buff=GAP)
        group.move_to(LEFT * 0.5)
    elif total_w > MAX_ROW_W:
        # Wrap: split into two rows
        half   = n // 2
        row1   = VGroup(*stage_cards[:half]).arrange(RIGHT, buff=GAP)
        row2   = VGroup(*stage_cards[half:]).arrange(RIGHT, buff=GAP)
        group  = VGroup(row1, row2).arrange(DOWN, buff=GAP * 2.5)
        group.move_to(DOWN * 0.3)
    else:
        group = VGroup(*stage_cards)
        group.arrange(RIGHT, buff=GAP)
        group.move_to(DOWN * 0.3)

    if group.width > MAX_ROW_W:
        group.scale_to_fit_width(MAX_ROW_W)

    return group, vertical


# ── Main render ────────────────────────────────────────────────────────────

def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    stages   = data["stages"]
    n        = len(stages)
    box_w    = min(2.4, 14.5 / n)
    recycle  = data.get("recycle")
    show_pulse    = data.get("show_pulse", True)
    spotlight_idx = data.get("spotlight_stage")   # int index to Indicate

    # ── Build cards ────────────────────────────────────────────────────
    cards, rects = [], []
    for i, stage in enumerate(stages):
        card, rect = _stage_card(stage, i, box_w)
        cards.append(card)
        rects.append(rect)

    # ── Layout ─────────────────────────────────────────────────────────
    layout_group, vertical = _layout(cards, rects, n, box_w)

    # ── Connector arrows ───────────────────────────────────────────────
    arrows: list[VGroup] = []
    conn_color = COLORS.get("text_muted", "#888888")

    for i in range(n - 1):
        if vertical:
            start = rects[i    ].get_bottom() + DOWN  * 0.06
            end   = rects[i + 1].get_top()    + UP    * 0.06
        else:
            start = rects[i    ].get_right()  + RIGHT * 0.06
            end   = rects[i + 1].get_left()   + LEFT  * 0.06

        lbl = stages[i].get("arrow_label", "")
        arrows.append(_connector_arrow(start, end, conn_color,
                                       lbl, vertical))

    mobs = [header, layout_group, *arrows]

    # ── Animate in ─────────────────────────────────────────────────────
    # All cards drop/grow in with a LaggedStart for snappier reveal
    scene.play(
        LaggedStart(
            *[FadeIn(c, scale=0.88) for c in cards],
            lag_ratio=0.12,
        ),
        run_time=max(0.6, n * 0.14),
    )

    # Arrows draw one-by-one with optional flow pulse
    for i, arr_group in enumerate(arrows):
        scene.play(GrowArrow(arr_group[0]), run_time=0.18)
        if len(arr_group) > 1:
            scene.play(FadeIn(arr_group[1]), run_time=0.12)
        if show_pulse:
            _pulse(scene, arr_group[0], col=SCI_PALETTE[i % len(SCI_PALETTE)])

    # ── Optional spotlight on a specific stage ─────────────────────────
    if spotlight_idx is not None and 0 <= spotlight_idx < n:
        col = _resolve(stages[spotlight_idx].get("color_key", ""), spotlight_idx)
        _spotlight(scene, cards[spotlight_idx], col)

    # ── Recycle arrow ──────────────────────────────────────────────────
    if recycle:
        from_idx  = recycle["from_idx"]
        to_idx    = recycle.get("to_idx", 0)
        rec_label = recycle.get("label", "repeat")

        arc, arc_lbl = _recycle_arc(
            cards, from_idx, to_idx, rec_label, vertical, rects,
        )
        scene.play(Create(arc), run_time=0.45)
        scene.play(FadeIn(arc_lbl), run_time=0.20)

        # Pulse travels the recycle arc as well
        if show_pulse:
            _pulse(scene, arc, color=RECYCLE_COLOR)

        mobs.extend([arc, arc_lbl])

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)

