"""Hook scene — attention-grabbing opening for social media."""

from __future__ import annotations
import numpy as np
from manim import *
from manimator.config import COLORS, TIMING, FONTS

# ── Design tokens ──────────────────────────────────────────────────────────
ACCENT       = "#4477AA"
ACCENT_HOT   = "#EE6677"    # second accent for counter / highlight words
PARTICLE_N   = 38           # number of ambient background particles
MAX_W        = 12.5         # max hook text width before scaling


# ── Helpers ────────────────────────────────────────────────────────────────

def _particle_field(n: int, seed: int = 0) -> VGroup:
    """
    Sparse field of small dots at random screen positions —
    adds depth without distracting from the text.
    """
    rng   = np.random.default_rng(seed)
    group = VGroup()
    for _ in range(n):
        x   = rng.uniform(-7.0,  7.0)
        y   = rng.uniform(-4.0,  4.0)
        r   = rng.uniform(0.018, 0.055)
        op  = rng.uniform(0.10,  0.35)
        col = ACCENT if rng.random() > 0.4 else ACCENT_HOT
        dot = Dot(point=[x, y, 0], radius=r, color=col, fill_opacity=op)
        group.add(dot)
    return group


def _word_mobjects(
    text: str, font_size: int, base_color: str,
    highlight_words: list[str],
) -> VGroup:
    """
    Splits the hook into individual word Text mobjects and
    highlights specific words in ACCENT_HOT.
    Words are laid out manually so each animates independently.
    """
    words = text.split()
    mobs  = VGroup()
    for w in words:
        clean = w.strip(".,!?")
        col   = ACCENT_HOT if clean in highlight_words else base_color
        wt    = Text(w, font_size=font_size, color=col, weight=BOLD)
        mobs.add(wt)
    # Horizontal layout with proper spacing
    mobs.arrange(RIGHT, buff=0.22)
    # Wrap to two lines if too wide
    if mobs.width > MAX_W:
        half    = len(mobs) // 2
        line1   = VGroup(*mobs[:half]).arrange(RIGHT, buff=0.22)
        line2   = VGroup(*mobs[half:]).arrange(RIGHT, buff=0.22)
        VGroup(line1, line2).arrange(DOWN, buff=0.35, aligned_edge=LEFT)
        mobs    = VGroup(line1, line2)
        # Scale if still too wide
        if mobs.width > MAX_W:
            mobs.scale_to_fit_width(MAX_W)
    return mobs


def _stat_counter(
    scene: Scene,
    value: float,
    suffix: str,
    color: str,
    duration: float = 0.8,
) -> DecimalNumber:
    """
    Animated rolling counter — effective for quantitative hooks
    like "94% accuracy" or "300× speed-up".
    """
    counter = DecimalNumber(
        0,
        num_decimal_places=0 if value >= 10 else 1,
        font_size=96,
        color=color,
        stroke_width=1.5,
    )
    suffix_mob = Text(suffix, font_size=52, color=color, weight=BOLD)
    group = VGroup(counter, suffix_mob).arrange(RIGHT, buff=0.15)
    group.move_to(ORIGIN)

    counter.add_updater(lambda m, dt: None)  # attach to scene update loop

    scene.play(
        ChangeDecimalValue(counter, value, run_time=duration,
                           rate_func=rush_from),
    )
    return group


def _radial_flash(scene: Scene, color: str = WHITE):
    """
    Expanding ring + white flash — a cinematic cut between hook and content.
    Far more impactful than a plain FadeOut.
    """
    ring = Circle(radius=0.01, color=color,
                  stroke_width=6, stroke_opacity=0.9)
    ring.move_to(ORIGIN)
    scene.play(
        ring.animate.scale(40).set_stroke(opacity=0),
        run_time=0.30,
        rate_func=rush_from,
    )
    scene.remove(ring)


def _scanline_reveal(scene: Scene, mob: VMobject, run_time: float = 0.5):
    """
    Vertical wipe reveal — clips the mob open from left to right
    using a Rectangle mask grown with GrowFromEdge.
    More kinetic than FadeIn for social hooks.
    """
    mask = mob.copy().set_opacity(0)
    scene.add(mask)
    scene.play(
        LaggedStart(
            *[FadeIn(sm, shift=DOWN * 0.08) for sm in mob],
            lag_ratio=0.08,
        ),
        run_time=run_time,
    )


# ── Main render ────────────────────────────────────────────────────────────

def render(scene: Scene, data: dict):
    hook_text   = data.get("hook_text", data.get("title", ""))
    subtitle    = data.get("subtitle", "")
    t           = data.get("timing", {})
    hl_words    = data.get("highlight_words", [])
    hook_fs     = data.get("font_size", 54)

    # ── Background ────────────────────────────────────────────────────
    scene.camera.background_color = COLORS["bg_dark"]

    particles = _particle_field(PARTICLE_N, seed=data.get("seed", 1))
    scene.add(particles)
    # Slow ambient drift upward
    scene.play(
        particles.animate.shift(UP * 0.06),
        run_time=0.01,   # just registers the animation target
    )

    # ── Accent geometry ───────────────────────────────────────────────
    # Two short bars that grow outward from centre — more dynamic than one line
    bar_l = Line(ORIGIN, LEFT  * 2.8, color=ACCENT,     stroke_width=4.5)
    bar_r = Line(ORIGIN, RIGHT * 2.8, color=ACCENT_HOT, stroke_width=4.5)
    bar_group = VGroup(bar_l, bar_r)

    # ── Hook text — word-by-word objects ──────────────────────────────
    hook_words = _word_mobjects(hook_text, hook_fs, WHITE, hl_words)
    hook_words.move_to(ORIGIN)

    # Position bar above hook
    bar_group.next_to(hook_words, UP, buff=0.55)

    # ── Optional stat counter (replaces hook text if present) ─────────
    stat_value  = data.get("stat_value")
    stat_suffix = data.get("stat_suffix", "%")
    mobs = [particles, bar_group, hook_words]

    # ── Animate in ────────────────────────────────────────────────────

    # 1. Bars snap outward from centre
    scene.play(
        GrowFromPoint(bar_l, bar_l.get_right()),
        GrowFromPoint(bar_r, bar_r.get_left()),
        run_time=t.get("bar_grow", 0.22),
        rate_func=rush_from,
    )

    # 2. Stat counter rolls (if provided), otherwise word-by-word text
    if stat_value is not None:
        counter_group = _stat_counter(
            scene, stat_value, stat_suffix,
            ACCENT_HOT,
            duration=t.get("counter_duration", 0.75),
        )
        counter_group.next_to(bar_group, DOWN, buff=0.55)
        mobs.append(counter_group)
        scene.add(counter_group)
        # Hook text appears below counter as context
        hook_words.next_to(counter_group, DOWN, buff=0.35)
        hook_words.scale(0.65)
        scene.play(
            FadeIn(hook_words, scale=1.04),
            run_time=t.get("title_fade", 0.35),
        )
    else:
        # Word-by-word kinetic reveal — each word pops in with slight scale
        flat_words = list(hook_words) if isinstance(hook_words[0], Text) \
                     else [w for line in hook_words for w in line]
        scene.play(
            LaggedStart(
                *[FadeIn(w, scale=1.12, rate_func=rush_from)
                  for w in flat_words],
                lag_ratio=t.get("word_lag", 0.09),
            ),
            run_time=t.get("title_fade", 0.55),
        )

    # 3. Subtitle fades in quietly
    sub_mob = VMobject()
    if subtitle:
        sub_mob = MarkupText(
            subtitle, font_size=26,
            color=COLORS.get("text_muted", GRAY),
        )
        sub_mob.next_to(hook_words, DOWN, buff=0.50)
        if sub_mob.width > MAX_W - 1:
            sub_mob.scale_to_fit_width(MAX_W - 1)
        scene.play(FadeIn(sub_mob, shift=UP * 0.08), run_time=0.28)
        mobs.append(sub_mob)

    # 4. Optional accent dot pulse on a highlight word
    if hl_words:
        flat = list(hook_words) if isinstance(hook_words[0], Text) \
               else [w for line in hook_words for w in line]
        targets = [w for w in flat
                   if isinstance(w, Text)
                   and any(h in w.text for h in hl_words)]
        if targets:
            pulse_dot = Dot(radius=0.07, color=ACCENT_HOT)
            pulse_dot.next_to(targets[0], UP, buff=0.08)
            scene.play(
                FadeIn(pulse_dot, scale=2.5, rate_func=rush_from),
                run_time=0.18,
            )
            scene.play(FadeOut(pulse_dot, scale=0.1), run_time=0.25)

    # ── Hold ──────────────────────────────────────────────────────────
    scene.wait(t.get("scene_pause", 0.7))

    # ── Exit: radial flash → content ─────────────────────────────────
    exit_style = data.get("exit_style", "flash")   # "flash" | "wipe" | "fade"

    if exit_style == "flash":
        scene.play(FadeOut(VGroup(*mobs)), run_time=0.15)
        _radial_flash(scene, color=WHITE)
    elif exit_style == "wipe":
        scene.play(
            VGroup(*mobs).animate.shift(LEFT * config.frame_width),
            rate_func=rush_into,
            run_time=t.get("transition", 0.28),
        )
    else:
        scene.play(
            FadeOut(VGroup(*mobs), shift=UP * 0.4),
            run_time=t.get("transition", 0.25),
        )

    scene.camera.background_color = COLORS["bg_main"]

