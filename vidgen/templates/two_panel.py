from manim import *
from vidgen.config import COLORS, TIMING, FONTS, SPACING
from vidgen.helpers import (
    create_section_header, make_card, bullet_list,
    fade_out_all, animate_callout,
)


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    # Left panel
    left_bg = make_card(8.0, 5.5, stroke_color=COLORS["blue"])
    lt = Text(data["left_title"], font_size=FONTS["card_title"],
              color=COLORS["blue"], weight=BOLD)
    lt.move_to(left_bg.get_top() + DOWN * SPACING["card_title_pad"])
    left_content = bullet_list(data["left_items"], COLORS["blue"],
                               FONTS["body_text"], max_chars=30)
    left_content.move_to(left_bg.get_center() + DOWN * 0.2)
    left_panel = VGroup(left_bg, lt, left_content)
    left_panel.to_edge(LEFT, buff=SPACING["page_left"]).shift(DOWN * 0.5)

    # Right panel
    right_bg = make_card(8.0, 5.5, stroke_color=COLORS["green"])
    rt = Text(data["right_title"], font_size=FONTS["card_title"],
              color=COLORS["green"], weight=BOLD)
    rt.move_to(right_bg.get_top() + DOWN * SPACING["card_title_pad"])
    right_content = bullet_list(data["right_items"], COLORS["green"],
                                FONTS["body_text"], max_chars=30)
    right_content.move_to(right_bg.get_center() + DOWN * 0.2)
    right_panel = VGroup(right_bg, rt, right_content)
    right_panel.to_edge(RIGHT, buff=SPACING["page_right"]).shift(DOWN * 0.5)

    mobs = [header, left_panel, right_panel]

    scene.play(Create(left_bg), FadeIn(lt), Create(right_bg), FadeIn(rt),
               run_time=TIMING["group_fade"])
    for row in left_content:
        scene.play(FadeIn(row, shift=RIGHT * 0.15), run_time=0.22)
    for row in right_content:
        scene.play(FadeIn(row, shift=RIGHT * 0.15), run_time=0.22)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)
