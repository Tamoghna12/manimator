from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import (
    create_section_header, fade_out_all, animate_callout, resolve_color,
)


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    bars_data = data["bars"]
    suffix = data.get("value_suffix", "")
    n = len(bars_data)
    max_val = max(b["value"] for b in bars_data)

    bar_width = min(1.8, 14.0 / n)
    max_height = 5.0
    base_y = -2.5

    # Axes
    y_axis = Line(
        [-(n * bar_width) / 2 - 0.5, base_y, 0],
        [-(n * bar_width) / 2 - 0.5, base_y + max_height + 0.5, 0],
        color=COLORS["text_muted"], stroke_width=1.5,
    )
    x_axis = Line(
        [-(n * bar_width) / 2 - 0.5, base_y, 0],
        [(n * bar_width) / 2 + 0.5, base_y, 0],
        color=COLORS["text_muted"], stroke_width=1.5,
    )

    bars_group = VGroup()
    bar_anims = []

    for i, bd in enumerate(bars_data):
        col = resolve_color(bd["color_key"])
        val = bd["value"]
        h = max_height * (val / max_val) if val > 0 else 0.1

        bar = Rectangle(width=bar_width * 0.75, height=h,
                        fill_color=col, fill_opacity=0.85, stroke_width=0)
        x_pos = (i - (n - 1) / 2) * (bar_width + 0.3)
        bar.move_to([x_pos, base_y + h / 2, 0])

        val_text = Text(f"{val}{suffix}", font_size=18, color=COLORS["text_dark"],
                        weight=BOLD)
        val_text.next_to(bar, UP, buff=0.15)

        label = Text(bd["label"], font_size=16, color=COLORS["text_body"])
        label.next_to(bar, DOWN, buff=0.15).shift(DOWN * 0.1)

        bar_group = VGroup(bar, val_text, label)
        bars_group.add(bar_group)
        bar_anims.append(GrowFromEdge(bar, DOWN))

    all_viz = VGroup(y_axis, x_axis, bars_group)
    all_viz.move_to(DOWN * 0.2)

    mobs = [header, all_viz]

    scene.play(Create(y_axis), Create(x_axis), run_time=0.4)
    scene.play(
        LaggedStart(*bar_anims, lag_ratio=0.1),
        run_time=0.8,
    )
    # Show labels and values
    for bg in bars_group:
        scene.play(FadeIn(bg[1]), FadeIn(bg[2]), run_time=0.15)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)
