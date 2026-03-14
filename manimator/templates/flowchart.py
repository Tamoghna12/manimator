import numpy as np
from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING, PALETTE
from manimator.helpers import (
    create_section_header, fade_out_all, animate_callout, resolve_color,
)


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    stages = data["stages"]
    n = len(stages)
    box_w = min(2.2, 15.0 / n)
    box_h = 1.5
    gap = 0.3

    stage_boxes = VGroup()
    for i, stage in enumerate(stages):
        col = resolve_color(stage["color_key"])
        bg_col = stage.get("bg", "#F5F5F5")
        bx = RoundedRectangle(
            width=box_w, height=box_h, corner_radius=0.12,
            fill_color=bg_col, fill_opacity=1.0,
            stroke_color=col, stroke_width=2.5,
        )
        txt = Text(stage["label"], font_size=15, color=col, weight=BOLD)
        txt.move_to(bx.get_center())
        stage_boxes.add(VGroup(bx, txt))

    stage_boxes.arrange(RIGHT, buff=gap)
    stage_boxes.move_to(DOWN * 0.3)

    if stage_boxes.width > 17.5:
        stage_boxes.scale(17.5 / stage_boxes.width)

    arrows = VGroup()
    for i in range(n - 1):
        arr = Arrow(
            stage_boxes[i].get_right(), stage_boxes[i + 1].get_left(),
            color=COLORS["text_muted"], stroke_width=2.5,
            buff=0.08, max_tip_length_to_length_ratio=0.2,
        )
        arrows.add(arr)

    mobs = [header, stage_boxes, arrows]

    for i, box in enumerate(stage_boxes):
        scene.play(FadeIn(box, scale=0.9), run_time=0.25)
        if i < len(arrows):
            scene.play(GrowArrow(arrows[i]), run_time=0.15)

    # Recycle arrow
    recycle = data.get("recycle")
    if recycle:
        from_idx = recycle["from_idx"]
        to_idx = recycle["to_idx"]
        r_start = stage_boxes[from_idx].get_bottom() + DOWN * 0.15
        r_end = stage_boxes[to_idx].get_bottom() + DOWN * 0.15
        r_arrow = CurvedArrow(r_start, r_end, angle=-PI / 3,
                               color=COLORS["purple"], stroke_width=2)
        r_label = Text(recycle.get("label", "Recycle"), font_size=12,
                       color=COLORS["purple"])
        r_label.next_to(r_arrow, DOWN, buff=0.1)
        scene.play(Create(r_arrow), FadeIn(r_label), run_time=0.5)
        mobs.extend([r_arrow, r_label])

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)
