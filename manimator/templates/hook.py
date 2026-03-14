"""Hook scene — attention-grabbing opening for social media."""

from manim import *
from manimator.config import COLORS, TIMING, FONTS


def render(scene: Scene, data: dict):
    hook_text = data.get("hook_text", data.get("title", ""))
    subtitle = data.get("subtitle", "")

    # Dark background for impact
    scene.camera.background_color = COLORS["bg_dark"]

    # Large, bold hook text — centered, white
    hook = Text(
        hook_text, font_size=data.get("font_size", 52),
        color=WHITE, weight=BOLD,
    )
    # Wrap long text
    if hook.width > 16:
        hook.scale(16 / hook.width)
    hook.move_to(ORIGIN)

    # Accent bar above
    bar = Line(LEFT * 3, RIGHT * 3, color=COLORS["blue"], stroke_width=5)
    bar.next_to(hook, UP, buff=0.6)

    # Subtitle below
    mobs = [bar, hook]
    if subtitle:
        sub = Text(subtitle, font_size=28, color=GRAY)
        sub.next_to(hook, DOWN, buff=0.5)
        mobs.append(sub)

    # Fast, punchy animation
    t = data.get("timing", {})
    scene.play(
        Create(bar),
        FadeIn(hook, scale=1.05),
        run_time=t.get("title_fade", 0.6),
    )
    if subtitle:
        scene.play(FadeIn(sub), run_time=0.3)

    scene.wait(t.get("scene_pause", 0.8))

    # Flash transition
    scene.play(
        FadeOut(VGroup(*mobs), shift=UP * 0.5),
        run_time=t.get("transition", 0.2),
    )
    # Reset background
    scene.camera.background_color = COLORS["bg_main"]
