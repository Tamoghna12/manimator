import numpy as np
from manim import *
from vidgen.config import COLORS, TIMING, FONTS, SPACING
from vidgen.helpers import (
    create_section_header, make_card, fade_out_all, animate_callout,
    resolve_color,
)


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    lt = data["left_track"]
    rt = data["right_track"]
    cb = data["center_block"]

    # Build track colors
    lt_col = resolve_color(lt["color_key"])
    rt_col = resolve_color(rt["color_key"])
    cb_col = resolve_color(cb["color_key"])

    bg_map = {
        "blue": "#E8F4FD", "green": "#E8F8F0", "orange": "#FFF8ED",
        "red": "#FFF0EE", "deep_red": "#FFF0EE", "purple": "#F3E8FF",
    }

    # Left track box
    left_box = make_card(4.5, 3.0, stroke_color=lt_col, stroke_width=2.5,
                         fill_color=bg_map.get(lt["color_key"], "#F5F5F5"))
    left_label = Text(lt["label"], font_size=18, color=lt_col, weight=BOLD)
    left_label.move_to(left_box.get_center() + UP * 0.4)
    left_sub = Text(lt.get("sublabel", ""), font_size=13, color=COLORS["text_muted"])
    left_sub.next_to(left_label, DOWN, buff=0.15)
    left_track = VGroup(left_box, left_label, left_sub)
    left_track.move_to(LEFT * 5.5 + DOWN * 0.5)

    # Right track box
    right_box = make_card(4.5, 3.0, stroke_color=rt_col, stroke_width=2.5,
                          fill_color=bg_map.get(rt["color_key"], "#F5F5F5"))
    right_label = Text(rt["label"], font_size=18, color=rt_col, weight=BOLD)
    right_label.move_to(right_box.get_center() + UP * 0.4)
    right_sub = Text(rt.get("sublabel", ""), font_size=13, color=COLORS["text_muted"])
    right_sub.next_to(right_label, DOWN, buff=0.15)
    right_track = VGroup(right_box, right_label, right_sub)
    right_track.move_to(RIGHT * 5.5 + DOWN * 0.5)

    # Center block
    center_box = make_card(4.5, 5.0, stroke_color=cb_col, stroke_width=3.0,
                           fill_color=bg_map.get(cb["color_key"], "#FFF8ED"))
    center_title = Text(cb["label"], font_size=20, color=cb_col, weight=BOLD)
    center_title.move_to(center_box.get_center() + UP * 1.5)

    items_group = VGroup()
    for item in cb.get("items", []):
        dot = Text("▸", font_size=14, color=cb_col)
        txt = Text(item, font_size=14, color=COLORS["text_body"])
        row = VGroup(dot, txt).arrange(RIGHT, buff=0.15)
        items_group.add(row)
    items_group.arrange(DOWN, buff=0.2, aligned_edge=LEFT)
    items_group.move_to(center_box.get_center() + DOWN * 0.2)

    center_block = VGroup(center_box, center_title, items_group)
    center_block.move_to(ORIGIN + DOWN * 0.5)

    # Arrows
    arrow_l = DoubleArrow(
        left_track.get_right() + RIGHT * 0.1,
        center_block.get_left() + LEFT * 0.1,
        color=lt_col, stroke_width=3, buff=0.1,
        max_tip_length_to_length_ratio=0.08,
    )
    arrow_r = DoubleArrow(
        center_block.get_right() + RIGHT * 0.1,
        right_track.get_left() + LEFT * 0.1,
        color=rt_col, stroke_width=3, buff=0.1,
        max_tip_length_to_length_ratio=0.08,
    )

    mobs = [header, left_track, right_track, center_block, arrow_l, arrow_r]

    scene.play(
        FadeIn(left_track, shift=LEFT * 0.3),
        FadeIn(right_track, shift=RIGHT * 0.3),
        run_time=0.8
    )
    scene.play(Create(center_box), FadeIn(center_title), run_time=0.6)
    scene.play(
        LaggedStart(*[FadeIn(row, shift=RIGHT * 0.1) for row in items_group],
                    lag_ratio=0.1),
        run_time=0.8
    )
    scene.play(GrowArrow(arrow_l), GrowArrow(arrow_r), run_time=0.5)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)
