from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import (
    create_section_header, make_card, bullet_list,
    fade_out_all, animate_callout,
)


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    bg = make_card(16.0, 6.0)
    bg.next_to(header, DOWN, buff=0.5).align_to(header, LEFT)

    card_title = Text(data["header"].split(". ", 1)[-1] if ". " in data["header"] else data["header"],
                      font_size=FONTS["card_title"], color=COLORS["blue"], weight=BOLD)
    card_title.move_to(bg.get_top() + DOWN * SPACING["card_title_pad"])

    content = bullet_list(data["items"], bullet_color=COLORS["blue"],
                          font_size=FONTS["body_text"], max_chars=60)
    content.move_to(bg.get_center() + DOWN * 0.15)

    mobs = [header, bg, card_title, content]

    scene.play(Create(bg), FadeIn(card_title), run_time=TIMING["group_fade"])
    for row in content:
        scene.play(FadeIn(row, shift=RIGHT * 0.15), run_time=0.22)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)
