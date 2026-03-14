import numpy as np
from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import (
    create_section_header, make_card, fade_out_all, animate_callout,
    resolve_color,
)


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    axes_labels = data["axes"]
    clusters = data["clusters"]

    # Build axes using Manim's Axes
    axes = Axes(
        x_range=[-5, 5, 1],
        y_range=[-4, 4, 1],
        x_length=10,
        y_length=6,
        axis_config={"color": COLORS["text_muted"], "stroke_width": 1.5},
        tips=False,
    )
    x_lab = Text(axes_labels[0], font_size=16, color=COLORS["text_muted"])
    x_lab.next_to(axes, DOWN, buff=0.3)
    y_lab = Text(axes_labels[1], font_size=16, color=COLORS["text_muted"])
    y_lab.next_to(axes, LEFT, buff=0.3).rotate(PI / 2)

    axes_group = VGroup(axes, x_lab, y_lab)
    axes_group.move_to(LEFT * 2 + DOWN * 0.3)

    np.random.seed(42)
    all_dots = VGroup()
    legend_items = VGroup()

    for ci, cluster in enumerate(clusters):
        col = resolve_color(cluster["color_key"])
        cx, cy = cluster["center"]
        spread = cluster.get("spread", 0.4)
        n = cluster.get("n", 20)

        dots = VGroup()
        for _ in range(n):
            x = cx + np.random.randn() * spread
            y = cy + np.random.randn() * spread
            pt = axes.c2p(x, y)
            dot = Dot(point=pt, radius=0.08, color=col, fill_opacity=0.8)
            dots.add(dot)
        all_dots.add(dots)

        # Legend entry
        leg_dot = Dot(radius=0.1, color=col)
        leg_text = Text(cluster["label"], font_size=14, color=COLORS["text_body"])
        leg_entry = VGroup(leg_dot, leg_text).arrange(RIGHT, buff=0.15)
        legend_items.add(leg_entry)

    legend_items.arrange(DOWN, buff=0.2, aligned_edge=LEFT)
    legend_bg = make_card(
        legend_items.width + 0.6, legend_items.height + 0.4,
        stroke_color=COLORS["border"],
    )
    legend_items.move_to(legend_bg.get_center())
    legend = VGroup(legend_bg, legend_items)
    legend.next_to(axes_group, RIGHT, buff=0.8).align_to(axes_group, UP)

    mobs = [header, axes_group, all_dots, legend]

    scene.play(Create(axes), FadeIn(x_lab), FadeIn(y_lab), run_time=0.6)

    for dots in all_dots:
        scene.play(
            LaggedStart(*[FadeIn(d, scale=0.5) for d in dots], lag_ratio=0.02),
            run_time=0.6,
        )

    scene.play(FadeIn(legend), run_time=0.4)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)
