from manim import *
from vidgen.config import COLORS, TIMING, FONTS, SPACING
from vidgen.helpers import (
    create_section_header, make_card, fade_out_all, animate_callout,
)


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    # Equation
    eq = MathTex(data["latex"], font_size=56, color=COLORS["text_dark"])
    eq.move_to(UP * 0.5)

    mobs = [header, eq]

    scene.play(Write(eq), run_time=1.5)

    # Explanation below
    if data.get("explanation"):
        exp_bg = make_card(14.0, 1.5, stroke_color=COLORS["blue"])
        exp_text = Text(data["explanation"], font_size=FONTS["body_text"],
                        color=COLORS["text_body"])
        exp_text.move_to(exp_bg.get_center())
        exp_group = VGroup(exp_bg, exp_text)
        exp_group.next_to(eq, DOWN, buff=0.8)
        mobs.append(exp_group)
        scene.play(Create(exp_bg), FadeIn(exp_text), run_time=0.6)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)
