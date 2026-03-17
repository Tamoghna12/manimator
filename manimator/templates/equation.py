from __future__ import annotations
from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import (
    create_section_header, make_card, fade_out_all, animate_callout,
)

# ── Palette for term colouring (Tol colorblind-safe) ──────────────────────
TERM_COLORS = [
    "#4477AA",   # blue
    "#EE6677",   # red
    "#228833",   # green
    "#CCBB44",   # yellow
    "#AA3377",   # purple
    "#EE8866",   # orange
    "#44BB99",   # teal
]


# ── Helpers ────────────────────────────────────────────────────────────────

def _color_terms(
    eq: MathTex,
    term_colors: list[dict],
):
    """
    Apply per-term colours to a MathTex.
    Each entry: { "substring": "\\sigma", "color": "#4477AA" }
    Uses set_color_by_tex for reliable submobject targeting.
    """
    for tc in term_colors:
        eq.set_color_by_tex(tc["substring"], tc["color"])


def _symbol_legend(
    symbols: list[dict],
    accent: str,
) -> VGroup:
    """
    Two-column symbol table. Each entry:
      { "symbol": "\\mu_x", "meaning": "specific growth rate (h⁻¹)" }
    Returns a VGroup ready for placement.
    """
    rows = VGroup()
    for sym in symbols:
        sym_mob = MathTex(sym["symbol"], font_size=18,
                          color=accent)
        eq_mob  = Text("—", font_size=15, color=COLORS["text_muted"])
        def_mob = MarkupText(sym["meaning"], font_size=15,
                             color=COLORS["text_body"])
        if def_mob.width > 6.5:
            def_mob.scale_to_fit_width(6.5)
        row = VGroup(sym_mob, eq_mob, def_mob).arrange(RIGHT, buff=0.22,
                                                        aligned_edge=UP)
        rows.add(row)
    rows.arrange(DOWN, buff=0.22, aligned_edge=LEFT)
    return rows


def _underbrace_label(
    eq: MathTex,
    substring: str,
    label_tex: str,
    color: str,
    direction: int = -1,   # -1 = below, +1 = above (use Brace direction)
) -> VGroup:
    """
    Adds a Brace + MathTex label under (or over) a substring in eq.
    Returns VGroup(brace, label) positioned relative to eq.
    """
    try:
        part   = eq.get_part_by_tex(substring)
    except Exception:
        return VGroup()
    brace  = Brace(part, direction=DOWN * direction,
                   color=color, buff=0.06)
    label  = brace.get_tex(label_tex, buff=0.1)
    label.set_color(color)
    label.scale(0.75)
    return VGroup(brace, label)


def _derivation_chain(
    scene: Scene,
    steps: list[str],
    font_size: int,
    term_colors_per_step: list[list[dict]],
    position: np.ndarray,
    run_time: float = 0.9,
) -> MathTex:
    """
    Animates a sequence of equation transformations using
    TransformMatchingTex so shared terms slide smoothly.
    Returns the final MathTex.
    """
    prev = MathTex(*steps[0], font_size=font_size,
                   color=COLORS["text_dark"])
    if term_colors_per_step:
        _color_terms(prev, term_colors_per_step[0])
    prev.move_to(position)
    scene.play(Write(prev), run_time=run_time)

    for i, step in enumerate(steps[1:], start=1):
        nxt = MathTex(*step, font_size=font_size,
                      color=COLORS["text_dark"])
        if i < len(term_colors_per_step):
            _color_terms(nxt, term_colors_per_step[i])
        nxt.move_to(position)
        scene.play(TransformMatchingTex(prev, nxt),
                   run_time=run_time * 0.85)
        prev = nxt

    return prev


def _focus_pulse(scene: Scene, mob: VMobject, color: str = WHITE):
    """
    Circumscribe + flash — draws attention to a single term or equation
    without permanently modifying the mob.
    """
    scene.play(
        Circumscribe(mob, color=color, fade_out=True,
                     stroke_width=2.5, run_time=0.7),
    )


# ── Main render ────────────────────────────────────────────────────────────

def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    font_size   = data.get("font_size", 54)
    term_colors = data.get("term_colors", [])   # list of {substring, color}
    symbols     = data.get("symbols", [])        # symbol legend entries
    braces      = data.get("braces", [])         # underbrace annotations
    steps       = data.get("derivation_steps")   # optional multi-step chain
    focus_terms = data.get("focus_terms", [])    # substrings to Circumscribe

    mobs = [header]

    # ── Main equation (or derivation chain) ───────────────────────────
    eq_pos = UP * (0.8 if symbols else 0.3)

    if steps:
        # Multi-step derivation: data["latex"] is step 0,
        # data["derivation_steps"] is a list of subsequent LaTeX strings.
        # Each step can be a string or list (for MathTex multi-arg colouring).
        all_steps = [[data["latex"]]] + [
            [s] if isinstance(s, str) else s for s in steps
        ]
        tc_per_step = data.get("term_colors_per_step",
                               [term_colors] + [[]] * len(steps))
        eq = _derivation_chain(
            scene, all_steps, font_size, tc_per_step,
            eq_pos, run_time=1.0,
        )
    else:
        # Single equation
        latex_arg = data["latex"]
        eq = MathTex(
            *([latex_arg] if isinstance(latex_arg, str) else latex_arg),
            font_size=font_size,
            color=COLORS["text_dark"],
        )
        if term_colors:
            _color_terms(eq, term_colors)
        eq.move_to(eq_pos)

        # Scale down if too wide
        if eq.width > 13.5:
            eq.scale_to_fit_width(13.5)

        scene.play(Write(eq, run_time=1.3, rate_func=linear))

    mobs.append(eq)

    # ── Underbrace annotations ────────────────────────────────────────
    brace_groups = []
    for b in braces:
        col = b.get("color", TERM_COLORS[0])
        bg  = _underbrace_label(
            eq,
            b["substring"],
            b["label"],
            col,
            direction=b.get("direction", -1),
        )
        if len(bg) > 0:
            brace_groups.append(bg)

    if brace_groups:
        scene.play(
            LaggedStart(
                *[GrowFromCenter(bg[0]) for bg in brace_groups],
                lag_ratio=0.15,
            ),
            run_time=0.5,
        )
        scene.play(
            LaggedStart(
                *[FadeIn(bg[1]) for bg in brace_groups],
                lag_ratio=0.15,
            ),
            run_time=0.4,
        )
        mobs.extend(brace_groups)

    # ── Focus pulses on key terms ─────────────────────────────────────
    for ft in focus_terms:
        col = ft.get("color", WHITE)
        try:
            part = eq.get_part_by_tex(ft["substring"])
            _focus_pulse(scene, part, color=col)
        except Exception:
            pass

    # ── Symbol legend ─────────────────────────────────────────────────
    if symbols:
        accent = data.get("legend_accent", TERM_COLORS[0])
        legend_rows = _symbol_legend(symbols, accent)

        # Separator rule between equation and legend
        sep_rule = Line(
            LEFT * 6.5, RIGHT * 6.5,
            stroke_width=0.7,
            color=COLORS["text_muted"],
            stroke_opacity=0.4,
        )

        leg_bg = make_card(
            legend_rows.width + 0.8,
            legend_rows.height + 0.45,
            stroke_color=COLORS["border"],
        )
        legend_rows.move_to(leg_bg)
        legend = VGroup(leg_bg, legend_rows)

        # Place below equation (with separator) or to the right if space allows
        avail_below = eq.get_bottom()[1] - (-3.8)
        if legend.height < avail_below - 0.6:
            sep_rule.next_to(eq, DOWN, buff=0.35)
            legend.next_to(sep_rule, DOWN, buff=0.30)
            scene.play(Create(sep_rule), run_time=0.25)
            mobs.append(sep_rule)
        else:
            legend.next_to(eq, RIGHT, buff=0.8).align_to(eq, UP)

        scene.play(FadeIn(legend, shift=UP * 0.10), run_time=0.4)

        # Stagger reveal of each row
        scene.play(
            LaggedStart(
                *[FadeIn(row, shift=RIGHT * 0.08)
                  for row in legend_rows],
                lag_ratio=0.10,
            ),
            run_time=max(0.4, len(legend_rows) * 0.09),
        )
        mobs.append(legend)

    # ── Explanation card ──────────────────────────────────────────────
    if data.get("explanation"):
        exp_text = MarkupText(
            data["explanation"],
            font_size=FONTS["body_text"],
            color=COLORS["text_body"],
        )
        if exp_text.width > 13.0:
            exp_text.scale_to_fit_width(13.0)

        # Coloured left-rule card (matches the bar chart / ref slide style)
        rule = Line(UP * 0.4, DOWN * 0.4,
                    stroke_width=3.5, color=TERM_COLORS[0])
        exp_inner = VGroup(rule, exp_text).arrange(RIGHT, buff=0.22)

        exp_bg = make_card(
            exp_inner.width + 0.55,
            exp_inner.height + 0.40,
            stroke_color=COLORS["blue"],
        )
        exp_inner.move_to(exp_bg)
        exp_group = VGroup(exp_bg, exp_inner)

        # Anchor below all prior content
        lowest = min(m.get_bottom()[1] for m in mobs if hasattr(m, "get_bottom"))
        exp_group.next_to([0, lowest, 0], DOWN, buff=0.30)

        scene.play(
            Create(exp_bg),
            FadeIn(rule),
            FadeIn(exp_text, shift=RIGHT * 0.10),
            run_time=0.55,
        )
        mobs.append(exp_group)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)

