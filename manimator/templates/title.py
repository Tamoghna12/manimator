from manim import *
from manimator.config import COLORS, TIMING, FONTS
from manimator.helpers import fade_out_all

# ── Design tokens ──────────────────────────────────────────────────────────
ACCENT       = "#4477AA"     # Tol blue, consistent across slides
ACCENT_LIGHT = "#66CCEE"
RULE_W       = 3.5
TITLE_FS     = 52
SUBTITLE_FS  = 26
META_FS      = 18
FOOT_FS      = 14


def _corner_accents() -> VGroup:
    """Four small L-shaped corner brackets — a common scientific poster motif."""
    arm = 0.35
    stroke = 1.6

    def bracket(flip_x: bool, flip_y: bool) -> VGroup:
        sx = -1 if flip_x else 1
        sy = -1 if flip_y else 1
        h_line = Line(ORIGIN, RIGHT * arm * sx, stroke_width=stroke, color=ACCENT)
        v_line = Line(ORIGIN, UP    * arm * sy, stroke_width=stroke, color=ACCENT)
        return VGroup(h_line, v_line)

    tl = bracket(False, False).move_to([-6.8,  3.6, 0])
    tr = bracket(True,  False).move_to([ 6.8,  3.6, 0])
    bl = bracket(False, True ).move_to([-6.8, -3.6, 0])
    br = bracket(True,  True ).move_to([ 6.8, -3.6, 0])
    return VGroup(tl, tr, bl, br)


def _rule_pair(width: float = 5.0) -> tuple[Line, Line]:
    """
    Two-segment animated rule: left half grows LEFT→RIGHT,
    right half grows RIGHT→LEFT, meeting at centre.
    More dynamic than a single Create(line).
    """
    left  = Line([0, 0, 0], [-width / 2, 0, 0],
                 color=ACCENT,       stroke_width=RULE_W)
    right = Line([0, 0, 0], [ width / 2, 0, 0],
                 color=ACCENT_LIGHT, stroke_width=RULE_W)
    return left, right


def _meta_row(icon_char: str, text: str, font_size: int = META_FS) -> VGroup:
    """Icon glyph + text on one line (author, affiliation, date…)."""
    icon = Text(icon_char, font_size=font_size + 2, color=ACCENT)
    body = Text(text,       font_size=font_size,     color=COLORS["text_body"])
    row  = VGroup(icon, body).arrange(RIGHT, buff=0.2)
    return row


def render(scene: Scene, data: dict):
    mobs = []

    # ── Corner decorations ────────────────────────────────────────────────
    corners = _corner_accents()
    scene.play(
        LaggedStart(*[FadeIn(c, scale=0.5) for c in corners], lag_ratio=0.08),
        run_time=0.4,
    )
    mobs.append(corners)

    # ── Background accent bar (thin horizontal bar, top-anchored) ─────────
    bg_bar = Rectangle(
        width=config.frame_width,
        height=0.06,
        fill_color=ACCENT,
        fill_opacity=0.7,
        stroke_width=0,
    ).to_edge(UP, buff=0)
    scene.play(GrowFromCenter(bg_bar), run_time=0.3)
    mobs.append(bg_bar)

    # ── Title ─────────────────────────────────────────────────────────────
    title = Text(
        data["title"],
        font_size=TITLE_FS,
        color=COLORS["text_dark"],
        weight=BOLD,
    )

    # Dynamically scale down if the title is too wide
    if title.width > config.frame_width - 1.5:
        title.scale_to_fit_width(config.frame_width - 1.5)

    # Write gives a much more intentional, "authored" feel than FadeIn [web:33]
    scene.play(Write(title, run_time=1.2, rate_func=linear))
    mobs.append(title)

    elements = [title]

    # ── Subtitle ──────────────────────────────────────────────────────────
    if data.get("subtitle"):
        subtitle = MarkupText(
            data["subtitle"],
            font_size=SUBTITLE_FS,
            color=COLORS["text_light"],
        )
        subtitle.next_to(title, DOWN, buff=0.45)
        scene.play(FadeIn(subtitle, shift=DOWN * 0.15), run_time=0.5)
        elements.append(subtitle)
        mobs.append(subtitle)

    # ── Animated split rule ───────────────────────────────────────────────
    rule_width = min(title.width + 1.0, config.frame_width - 1.0)
    left_rule, right_rule = _rule_pair(rule_width)
    rule_group = VGroup(left_rule, right_rule)
    rule_group.next_to(elements[-1], DOWN, buff=0.45)

    scene.play(
        GrowFromPoint(left_rule,  left_rule.get_right()),   # grows outward left
        GrowFromPoint(right_rule, right_rule.get_left()),   # grows outward right
        run_time=0.45,
    )
    elements.append(rule_group)
    mobs.append(rule_group)

    # ── Author / Affiliation / Date meta rows ─────────────────────────────
    meta_rows = VGroup()

    if data.get("authors"):
        meta_rows.add(_meta_row("✦", data["authors"]))
    if data.get("affiliation"):
        meta_rows.add(_meta_row("⬡", data["affiliation"]))
    if data.get("date"):
        meta_rows.add(_meta_row("◷", data["date"]))

    if len(meta_rows) > 0:
        meta_rows.arrange(DOWN, buff=0.22, aligned_edge=LEFT)
        meta_rows.next_to(rule_group, DOWN, buff=0.42)
        meta_rows.shift(RIGHT * (title.get_left()[0] - meta_rows.get_left()[0]))

        scene.play(
            LaggedStart(
                *[FadeIn(row, shift=RIGHT * 0.10) for row in meta_rows],
                lag_ratio=0.18,
            ),
            run_time=0.6,
        )
        elements.append(meta_rows)
        mobs.append(meta_rows)

    # ── Centre the full composition (excluding fixed bg elements) ─────────
    comp = VGroup(*[e for e in elements])
    scene.play(
        comp.animate.move_to(ORIGIN + UP * (0.3 if len(meta_rows) else 0)),
        run_time=0.35,
    )

    # ── Footnote (pinned to bottom, independent of centring) ─────────────
    if data.get("footnote"):
        foot = MarkupText(
            data["footnote"],
            font_size=FOOT_FS,
            color=COLORS["text_muted"],
        )
        foot.to_edge(DOWN, buff=0.35)
        scene.play(FadeIn(foot), run_time=0.3)
        mobs.append(foot)

    # ── Accent dot pulse on title (optional, triggers if data flag set) ───
    if data.get("pulse_accent", False):
        dot = Dot(radius=0.08, color=ACCENT_LIGHT).next_to(title, RIGHT, buff=0.15)
        scene.play(
            FadeIn(dot, scale=2.5, rate_func=rush_from),
            run_time=0.25,
        )
        scene.play(FadeOut(dot, scale=0.1), run_time=0.4)
        # dot is transient — not added to mobs

    scene.wait(TIMING.get("scene_pause", 2.5))
    fade_out_all(scene, mobs)

