from manim import *
from vidgen.config import COLORS, TIMING, FONTS
from vidgen.helpers import fade_out_all


def render(scene: Scene, data: dict):
    title = Text(data["title"], font_size=52, color=COLORS["text_dark"], weight=BOLD)
    mobs = [title]

    elements = [title]
    if data.get("subtitle"):
        subtitle = Text(data["subtitle"], font_size=28, color=COLORS["text_light"])
        subtitle.next_to(title, DOWN, buff=0.4)
        elements.append(subtitle)
        mobs.append(subtitle)

    line = Line(LEFT * 4, RIGHT * 4, color=COLORS["blue"], stroke_width=3)
    line.next_to(elements[-1], DOWN, buff=0.4)
    elements.append(line)
    mobs.append(line)

    if data.get("footnote"):
        ref = Text(data["footnote"], font_size=FONTS["footnote"],
                   color=COLORS["text_muted"])
        ref.next_to(line, DOWN, buff=0.4)
        elements.append(ref)
        mobs.append(ref)

    # Center the group
    g = VGroup(*elements)
    g.move_to(ORIGIN)

    # Animate sequentially
    scene.play(FadeIn(title, shift=DOWN * 0.3), run_time=1.0)
    for el in elements[1:]:
        scene.play(FadeIn(el), run_time=0.5)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)
