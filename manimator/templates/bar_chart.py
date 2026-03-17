from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import (
    create_section_header, fade_out_all, animate_callout, resolve_color,
)

# ── Scientific colour palette (Paul Tol's colorblind-safe set) ──────────────
SCI_PALETTE = {
    "tol_blue":       "#4477AA",
    "tol_cyan":       "#66CCEE",
    "tol_green":      "#228833",
    "tol_yellow":     "#CCBB44",
    "tol_red":        "#EE6677",
    "tol_purple":     "#AA3377",
    "tol_grey":       "#BBBBBB",
    "tol_orange":     "#EE8866",
    "tol_teal":       "#44BB99",
    "tol_indigo":     "#6655A8",
}

DEFAULT_CYCLE = list(SCI_PALETTE.values())


def _resolve(color_key: str) -> str:
    """Resolve from palette, fallback to resolve_color helper, then raw hex."""
    if color_key in SCI_PALETTE:
        return SCI_PALETTE[color_key]
    try:
        return resolve_color(color_key)
    except Exception:
        return color_key  # assume raw hex / named colour


def _make_yticks(
    base_y: float,
    max_height: float,
    max_val: float,
    x_left: float,
    n_ticks: int = 5,
) -> VGroup:
    """Horizontal grid lines + numeric tick labels on the Y-axis."""
    group = VGroup()
    for i in range(1, n_ticks + 1):
        frac = i / n_ticks
        y = base_y + frac * max_height
        tick_val = max_val * frac

        # dotted grid line
        grid = DashedLine(
            [x_left, y, 0],
            [x_left + 14.0, y, 0],
            dash_length=0.08,
            dashed_ratio=0.4,
            color=COLORS["text_muted"],
            stroke_width=0.6,
            stroke_opacity=0.45,
        )
        # tick label (use MathTex for a polished scientific look)
        label_str = (
            f"{tick_val:.1f}" if tick_val < 1000 else f"{tick_val/1000:.1f}k"
        )
        tick_label = MathTex(
            label_str, font_size=14, color=COLORS["text_muted"]
        ).next_to([x_left, y, 0], LEFT, buff=0.15)

        group.add(grid, tick_label)
    return group


def _make_error_bar(bar: Rectangle, error: float, max_val: float,
                    max_height: float, base_y: float) -> VGroup:
    """± error bar drawn above the rectangle centre."""
    if error <= 0:
        return VGroup()
    px_error = max_height * (error / max_val)
    cx = bar.get_center()[0]
    top = bar.get_top()[1]
    cap_w = bar.width * 0.25

    stem = Line([cx, top - px_error, 0], [cx, top + px_error, 0],
                color=WHITE, stroke_width=1.5)
    cap_top = Line([cx - cap_w, top + px_error, 0],
                   [cx + cap_w, top + px_error, 0],
                   color=WHITE, stroke_width=1.5)
    cap_bot = Line([cx - cap_w, top - px_error, 0],
                   [cx + cap_w, top - px_error, 0],
                   color=WHITE, stroke_width=1.5)
    return VGroup(stem, cap_top, cap_bot)


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    bars_data   = data["bars"]
    suffix      = data.get("value_suffix", "")
    x_label_str = data.get("x_axis_label", "")
    y_label_str = data.get("y_axis_label", "")
    n           = len(bars_data)
    max_val     = max(b["value"] for b in bars_data)

    # ── Layout constants ──────────────────────────────────────────────────
    bar_width  = min(1.6, 13.0 / n)
    max_height = 4.5
    base_y     = -2.5
    x_left     = -(n * bar_width) / 2 - 0.8
    x_right    = (n * bar_width) / 2 + 0.8

    # ── Axes ──────────────────────────────────────────────────────────────
    y_axis = Line(
        [x_left, base_y, 0],
        [x_left, base_y + max_height + 0.6, 0],
        color=COLORS["text_muted"], stroke_width=1.8,
    )
    x_axis = Line(
        [x_left, base_y, 0],
        [x_right, base_y, 0],
        color=COLORS["text_muted"], stroke_width=1.8,
    )

    # Axis arrowheads (scientific convention)
    y_arrow = Arrow(
        [x_left, base_y + max_height + 0.3, 0],
        [x_left, base_y + max_height + 0.7, 0],
        buff=0, color=COLORS["text_muted"],
        stroke_width=1.8, max_tip_length_to_length_ratio=0.4,
    )
    x_arrow = Arrow(
        [x_right - 0.1, base_y, 0],
        [x_right + 0.3, base_y, 0],
        buff=0, color=COLORS["text_muted"],
        stroke_width=1.8, max_tip_length_to_length_ratio=0.4,
    )

    # Axis labels (LaTeX)
    y_tex = MathTex(y_label_str, font_size=20, color=COLORS["text_body"]) \
        .next_to(y_arrow, UP, buff=0.1) if y_label_str else VMobject()
    x_tex = MathTex(x_label_str, font_size=20, color=COLORS["text_body"]) \
        .next_to([x_right + 0.3, base_y, 0], RIGHT, buff=0.1) if x_label_str else VMobject()

    # Y-axis grid + ticks
    yticks = _make_yticks(base_y, max_height, max_val, x_left)

    # ── Bars ──────────────────────────────────────────────────────────────
    bars_group = VGroup()
    bar_anims  = []
    err_groups = VGroup()

    for i, bd in enumerate(bars_data):
        # Color: prefer explicit color_key, else auto-cycle through SCI_PALETTE
        ck  = bd.get("color_key", DEFAULT_CYCLE[i % len(DEFAULT_CYCLE)])
        col = _resolve(ck)
        val = bd["value"]
        h   = max_height * (val / max_val) if val > 0 else 0.05

        x_pos = (i - (n - 1) / 2) * (bar_width + 0.35)

        # Bar with subtle gradient-like border highlight
        bar = Rectangle(
            width=bar_width * 0.78, height=h,
            fill_color=col, fill_opacity=0.88,
            stroke_color=col, stroke_width=0.8, stroke_opacity=0.5,
        )
        bar.move_to([x_pos, base_y + h / 2, 0])

        # Value label – MathTex for units/superscripts
        val_str = f"{val}{suffix}" if suffix else f"{val:.3g}"
        val_text = MathTex(val_str, font_size=17, color=COLORS["text_dark"]) \
            .next_to(bar, UP, buff=0.18)

        # Category label
        label = Text(
            bd["label"], font_size=15,
            color=COLORS["text_body"], weight=NORMAL,
        ).next_to(bar, DOWN, buff=0.2)

        # Optional n= annotation (sample size — common in science)
        n_label = VMobject()
        if "n" in bd:
            n_label = MathTex(
                f"n={bd['n']}", font_size=12, color=COLORS["text_muted"]
            ).next_to(label, DOWN, buff=0.08)

        bar_group = VGroup(bar, val_text, label, n_label)
        bars_group.add(bar_group)
        bar_anims.append(GrowFromEdge(bar, DOWN))

        # Error bars (optional – expects bd["error"])
        err = bd.get("error", 0)
        err_groups.add(_make_error_bar(bar, err, max_val, max_height, base_y))

    # ── Significance brackets (optional) ─────────────────────────────────
    sig_group = VGroup()
    for sb in data.get("significance_brackets", []):
        i1, i2 = sb["between"]
        stars   = sb.get("label", "*")
        b1 = bars_group[i1][0]
        b2 = bars_group[i2][0]
        y_top = max(b1.get_top()[1], b2.get_top()[1]) + 0.35
        x1, x2 = b1.get_center()[0], b2.get_center()[0]
        bracket = VGroup(
            Line([x1, y_top - 0.15, 0], [x1, y_top, 0], stroke_width=1.2, color=WHITE),
            Line([x1, y_top, 0],        [x2, y_top, 0], stroke_width=1.2, color=WHITE),
            Line([x2, y_top, 0], [x2, y_top - 0.15, 0], stroke_width=1.2, color=WHITE),
            MathTex(stars, font_size=18, color=WHITE).move_to(
                [(x1 + x2) / 2, y_top + 0.2, 0]
            ),
        )
        sig_group.add(bracket)

    # ── Assemble and shift into frame ─────────────────────────────────────
    all_viz = VGroup(y_axis, x_axis, y_arrow, x_arrow,
                     y_tex, x_tex, yticks, bars_group)
    all_viz.move_to(DOWN * 0.3)

    mobs = [header, all_viz, err_groups, sig_group]

    # ── Animation sequence ────────────────────────────────────────────────
    scene.play(
        Create(y_axis), Create(x_axis),
        FadeIn(y_arrow), FadeIn(x_arrow),
        FadeIn(y_tex), FadeIn(x_tex),
        run_time=0.5,
    )
    scene.play(FadeIn(yticks), run_time=0.3)
    scene.play(
        LaggedStart(*bar_anims, lag_ratio=0.12),
        run_time=max(0.6, n * 0.12),
    )
    # Reveal labels, values, sample sizes
    for bg in bars_group:
        scene.play(
            FadeIn(bg[1]), FadeIn(bg[2]), FadeIn(bg[3]),
            run_time=0.12,
        )
    # Error bars pop in after bars are established
    if any(len(eg) > 0 for eg in err_groups):
        scene.play(LaggedStart(
            *[FadeIn(eg) for eg in err_groups if len(eg) > 0],
            lag_ratio=0.1,
        ), run_time=0.4)
    # Significance brackets last
    if len(sig_group) > 0:
        scene.play(FadeIn(sig_group), run_time=0.35)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)

