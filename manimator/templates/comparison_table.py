from __future__ import annotations
import re
from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import (
    create_section_header, fade_out_all,
    animate_callout, resolve_color,
)

# ── Design tokens ──────────────────────────────────────────────────────────
SCI_PALETTE   = ["#4477AA","#EE6677","#228833","#CCBB44","#AA3377","#EE8866","#44BB99"]
CELL_H        = 0.70
HEADER_H      = 0.78
CORNER_R      = 0.06
MAX_TABLE_W   = 15.8
ZEBRA_ALPHA   = 0.04
HIGHLIGHT_ALPHA = 0.16
TAG_FS        = 11
ICON_MAP      = {
    "✔": ("#228833", "✔"),  "yes": ("#228833", "✔"),
    "✘": ("#EE6677", "✘"),  "no":  ("#EE6677", "✘"),
    "~": ("#CCBB44", "~"),  "optional": ("#CCBB44", "opt"),
    "n.s.": ("#888888", "n.s."),
    "***":  ("#EE6677", "***"),
    "**":   ("#EE8866", "**"),
    "*":    ("#CCBB44", "*"),
    "best": ("#228833", "best"),
    "default": ("#4477AA", "default"),
    "new":  ("#AA3377", "new"),
}


# ── Helpers ────────────────────────────────────────────────────────────────

def _is_numeric(text: str) -> bool:
    return bool(re.fullmatch(r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?", text.strip()))


def _numeric_color(value: float, lo: float, hi: float, low_is_good: bool) -> str:
    """Map a scalar to green-yellow-red based on range."""
    if hi == lo:
        return COLORS.get("text_body", "#333333")
    t = (value - lo) / (hi - lo)          # 0 = low, 1 = high
    if low_is_good:
        t = 1 - t
    if t > 0.6:
        return "#228833"
    if t > 0.35:
        return "#CCBB44"
    return "#EE6677"


def _col_widths_from_content(
    all_data: list[list[str]],
    total_w: float,
    min_frac: float = 0.08,
) -> list[float]:
    """
    Estimate column widths proportional to max cell character count,
    with a floor of `min_frac * total_w` per column. [content-aware]
    """
    n_cols = len(all_data[0])
    max_chars = [
        max(len(str(row[j])) for row in all_data if j < len(row))
        for j in range(n_cols)
    ]
    total_chars = sum(max_chars)
    raw = [total_w * (c / total_chars) for c in max_chars]
    floor = min_frac * total_w
    widths = [max(r, floor) for r in raw]
    # Re-normalise to exactly total_w
    scale = total_w / sum(widths)
    return [w * scale for w in widths]


def _tag_pill(text: str, color: str, font_size: int = TAG_FS) -> VGroup:
    lbl = Text(text, font_size=font_size, color=color, weight=BOLD)
    bg  = RoundedRectangle(
        width=lbl.width + 0.18, height=lbl.height + 0.10,
        corner_radius=0.05,
        fill_color=color, fill_opacity=0.20,
        stroke_color=color, stroke_width=0.8,
    )
    lbl.move_to(bg)
    return VGroup(bg, lbl)


def _cell_content(
    raw_text: str,
    is_header: bool,
    col_idx: int,
    max_w: float,
    col_align: str,          # "left" | "center" | "right"
    numeric_meta: dict,      # {col_idx: (lo, hi, low_is_good)}
) -> VGroup:
    """
    Build cell content mobject supporting:
      • ✔/✘ icon substitution
      • Tag pills (e.g. "best", "default", "new")
      • Numeric colour coding
      • MarkupText for <b>/<i> in header cells
      • Overflow-safe scaling
    """
    text = str(raw_text).strip()
    key  = text.lower()
    pad  = max_w - 0.22

    # ── Header: MarkupText + accent underline ──────────────────────────
    if is_header:
        col = SCI_PALETTE[col_idx % len(SCI_PALETTE)]
        mob = MarkupText(
            text, font_size=FONTS.get("table_header", 18),
            color=COLORS.get("text_dark", "#1A1A1A"), weight=BOLD,
        )
        if mob.width > pad:
            mob.scale_to_fit_width(pad)
        return VGroup(mob)

    # ── Icon substitution ──────────────────────────────────────────────
    if key in ICON_MAP:
        icon_color, icon_char = ICON_MAP[key]
        pill = _tag_pill(icon_char, icon_color)
        if pill.width > pad:
            pill.scale_to_fit_width(pad)
        return VGroup(pill)

    # ── Numeric colour coding ──────────────────────────────────────────
    if _is_numeric(text) and col_idx in numeric_meta:
        lo, hi, lig = numeric_meta[col_idx]
        num_color = _numeric_color(float(text), lo, hi, lig)
        mob = Text(
            text,
            font_size=FONTS.get("table_cell", 16),
            color=num_color, weight=BOLD,
            font="JetBrains Mono",
        )
        if mob.width > pad:
            mob.scale_to_fit_width(pad)
        return VGroup(mob)

    # ── Plain cell ─────────────────────────────────────────────────────
    mob = Text(
        text,
        font_size=FONTS.get("table_cell", 16),
        color=COLORS.get("text_body", "#333333"),
    )
    if mob.width > pad:
        mob.scale_to_fit_width(pad)
    return VGroup(mob)


def _align_in_cell(mob: VGroup, cell: VMobject, align: str) -> None:
    """Align content horizontally within a cell."""
    if align == "left":
        mob.move_to(cell.get_left() + RIGHT * (mob.width / 2 + 0.12))
    elif align == "right":
        mob.move_to(cell.get_right() + LEFT * (mob.width / 2 + 0.12))
    else:
        mob.move_to(cell.get_center())


# ── Main render ────────────────────────────────────────────────────────────

def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    columns     = data["columns"]
    rows        = data["rows"]
    n_cols      = len(columns)
    all_data    = [columns] + rows

    # ── Column configuration ───────────────────────────────────────────
    col_aligns: list[str] = data.get("col_aligns", ["center"] * n_cols)
    while len(col_aligns) < n_cols:
        col_aligns.append("center")

    # Highlighted rows (0-indexed into `rows`, not all_data)
    highlight_rows: set[int] = set(data.get("highlight_rows", []))

    # Numeric colour-coding: {col_idx: {"low_is_good": bool}}
    numeric_cols: dict[int, dict] = data.get("numeric_cols", {})

    # ── Column widths ──────────────────────────────────────────────────
    col_widths: list[float] = data.get("col_widths") or _col_widths_from_content(
        all_data, MAX_TABLE_W,
    )

    # ── Compute numeric ranges for colour coding ───────────────────────
    numeric_meta: dict[int, tuple] = {}
    for ci_str, cfg in numeric_cols.items():
        ci = int(ci_str)
        vals = []
        for row in rows:
            if ci < len(row) and _is_numeric(str(row[ci])):
                vals.append(float(row[ci]))
        if len(vals) >= 2:
            numeric_meta[ci] = (min(vals), max(vals), cfg.get("low_is_good", True))

    # ── Accent colour (one per column, cycling) ────────────────────────
    accent = SCI_PALETTE[0]
    try:
        accent = resolve_color(data.get("accent_color", ""))
    except Exception:
        pass

    # ── Build table ────────────────────────────────────────────────────
    cell_rows: list[VGroup] = []    # one VGroup per row (for animation)

    x_offsets = []
    cursor = -sum(col_widths) / 2
    for w in col_widths:
        x_offsets.append(cursor + w / 2)
        cursor += w

    n_rows_total = len(all_data)
    col_dividers = VGroup()

    for i, row_data in enumerate(all_data):
        is_header = i == 0
        data_row_idx = i - 1         # index into `rows`
        is_highlighted = (not is_header) and (data_row_idx in highlight_rows)
        is_zebra = (not is_header) and (not is_highlighted) and (data_row_idx % 2 == 1)

        h = HEADER_H if is_header else CELL_H
        y = (n_rows_total / 2 - i - 0.5) * CELL_H + (HEADER_H - CELL_H) / 2 * (1 if is_header else 0)
        # More precise: accumulate y from top
        y_top  = sum(HEADER_H if k == 0 else CELL_H for k in range(i))
        y_cent = -(y_top + h / 2 - (HEADER_H + CELL_H * (n_rows_total - 1)) / 2)

        row_group = VGroup()

        for j, cell_text in enumerate(row_data):
            w   = col_widths[j]
            xc  = x_offsets[j]

            # Cell background
            if is_header:
                fill_col = accent
                fill_op  = 0.22
                stroke_w = 2.0
            elif is_highlighted:
                fill_col = accent
                fill_op  = HIGHLIGHT_ALPHA
                stroke_w = 1.8
            elif is_zebra:
                fill_col = COLORS.get("text_muted", "#999999")
                fill_op  = ZEBRA_ALPHA
                stroke_w = 0.8
            else:
                fill_col = COLORS.get("bg_card", "#FFFFFF")
                fill_op  = 1.0
                stroke_w = 0.8

            cell_rect = RoundedRectangle(
                width=w, height=h, corner_radius=CORNER_R,
                fill_color=fill_col, fill_opacity=fill_op,
                stroke_color=COLORS.get("border", "#E0E0E0"),
                stroke_width=stroke_w,
            )
            cell_rect.move_to(RIGHT * xc + UP * y_cent)

            # Left accent bar on header row
            if is_header and j == 0:
                accent_bar = Rectangle(
                    width=0.06, height=h,
                    fill_color=accent, fill_opacity=1.0,
                    stroke_width=0,
                ).move_to(cell_rect.get_left() + RIGHT * 0.03)
                row_group.add(accent_bar)

            # Highlighted row: left indicator bar
            if is_highlighted and j == 0:
                ind_bar = Rectangle(
                    width=0.05, height=h,
                    fill_color=accent, fill_opacity=0.7,
                    stroke_width=0,
                ).move_to(cell_rect.get_left() + RIGHT * 0.025)
                row_group.add(ind_bar)

            content = _cell_content(
                str(cell_text), is_header, j, w,
                col_aligns[j], numeric_meta,
            )
            _align_in_cell(content, cell_rect, col_aligns[j] if not is_header else "center")

            row_group.add(cell_rect, content)

        cell_rows.append(row_group)

    # ── Column separator lines ─────────────────────────────────────────
    table_h = HEADER_H + CELL_H * (n_rows_total - 1)
    table_top = UP * (table_h / 2)
    for j in range(1, n_cols):
        xd = x_offsets[j] - col_widths[j] / 2
        col_dividers.add(
            Line(
                RIGHT * xd + table_top,
                RIGHT * xd + DOWN * table_h,
                stroke_width=0.6,
                color=COLORS.get("border", "#E0E0E0"),
                stroke_opacity=0.5,
            )
        )

    # ── Position entire table ──────────────────────────────────────────
    table_group = VGroup(*cell_rows, col_dividers)
    table_group.move_to(DOWN * 0.35)

    mobs: list[VMobject] = [header, table_group]

    # ── Animate in ────────────────────────────────────────────────────
    # Header row snaps in; data rows stagger in one-by-one
    scene.play(
        FadeIn(cell_rows[0], scale=0.96),
        run_time=0.35,
    )
    scene.play(Create(col_dividers), run_time=0.25)

    if len(cell_rows) > 1:
        scene.play(
            LaggedStart(
                *[FadeIn(row, shift=RIGHT * 0.08) for row in cell_rows[1:]],
                lag_ratio=0.10,
            ),
            run_time=max(0.5, len(cell_rows) * 0.12),
        )

    # ── Significance brackets (optional) ──────────────────────────────
    brackets = data.get("significance_brackets", [])
    bracket_mobs: list[VMobject] = []
    for br in brackets:
        between = br.get("between", [])   # [row_idx_a, row_idx_b] (0-indexed into rows)
        label   = br.get("label", "")
        if len(between) != 2:
            continue
        a_idx, b_idx = between
        ri_a = min(a_idx, b_idx) + 1      # +1 for header row
        ri_b = max(a_idx, b_idx) + 1

        if ri_a >= len(cell_rows) or ri_b >= len(cell_rows):
            continue

        x_bk   = x_offsets[-1] + col_widths[-1] / 2 + 0.18
        y_a    = cell_rows[ri_a].get_center()[1]
        y_b    = cell_rows[ri_b].get_center()[1]
        bk_col = "#EE6677" if "***" in label else COLORS.get("text_muted", "#999999")

        bk = VGroup(
            Line(RIGHT * x_bk + UP * y_a, RIGHT * x_bk + UP * y_b,
                 stroke_width=1.4, color=bk_col),
            Line(RIGHT * x_bk + UP * y_a,
                 RIGHT * (x_bk - 0.10) + UP * y_a,
                 stroke_width=1.4, color=bk_col),
            Line(RIGHT * x_bk + UP * y_b,
                 RIGHT * (x_bk - 0.10) + UP * y_b,
                 stroke_width=1.4, color=bk_col),
        )
        lbl = Text(label, font_size=12, color=bk_col, weight=BOLD)
        lbl.next_to(bk, RIGHT, buff=0.08)

        scene.play(Create(bk), FadeIn(lbl), run_time=0.35)
        bracket_mobs.extend([bk, lbl])

    mobs.extend(bracket_mobs)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)

