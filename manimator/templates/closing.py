from manim import *
from manimator.config import COLORS, TIMING, FONTS
from manimator.helpers import fade_out_all


def render(scene: Scene, data: dict):
    title = Text(data.get("title", "Key References"),
                 font_size=FONTS["scene_title"], color=COLORS["text_dark"], weight=BOLD)
    title.to_edge(UP, buff=1.0)
    scene.play(FadeIn(title), run_time=0.5)

    refs = data.get("references", [])
    ref_group = VGroup()
    for i, ref in enumerate(refs):
        num = Text(f"[{i + 1}]", font_size=16, color=COLORS["blue"], weight=BOLD)
        txt = Text(ref, font_size=18, color=COLORS["text_body"])
        row = VGroup(num, txt).arrange(RIGHT, buff=0.3)
        ref_group.add(row)

    ref_group.arrange(DOWN, buff=0.35, aligned_edge=LEFT)
    ref_group.move_to(ORIGIN)

    mobs = [title, ref_group]

    scene.play(
        LaggedStart(*[FadeIn(row, shift=RIGHT * 0.15) for row in ref_group],
                    lag_ratio=0.12),
        run_time=1.2
    )
    scene.wait(3.0)
    fade_out_all(scene, mobs)
