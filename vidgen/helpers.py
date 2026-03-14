"""Reusable Manim helper functions for all templates."""

from manim import *
from vidgen.config import COLORS, FONTS, SPACING, TIMING, PALETTE


def create_section_header(title: str) -> VGroup:
    header = Text(title, font_size=FONTS["section_header"],
                  color=COLORS["blue"], weight=BOLD)
    underline = Line(LEFT * header.width / 2, RIGHT * header.width / 2,
                     color=COLORS["blue"], stroke_width=2)
    underline.next_to(header, DOWN, buff=0.15)
    g = VGroup(header, underline)
    g.to_edge(UP, buff=SPACING["page_top"]).to_edge(LEFT, buff=SPACING["page_left"])
    return g


def make_card(width, height, stroke_color=None, stroke_width=1.5,
              fill_color=None, fill_opacity=1.0, radius=0.15):
    sc = stroke_color or COLORS["border"]
    fc = fill_color or COLORS["bg_card"]
    return RoundedRectangle(
        width=width, height=height, corner_radius=radius,
        fill_color=fc, fill_opacity=fill_opacity,
        stroke_color=sc, stroke_width=stroke_width,
    )


def wrap_lines(text: str, max_chars: int) -> list:
    words = text.split()
    lines, cur, n = [], [], 0
    for w in words:
        add = len(w) + (1 if cur else 0)
        if cur and n + add > max_chars:
            lines.append(" ".join(cur))
            cur, n = [w], len(w)
        else:
            cur.append(w)
            n += add
    if cur:
        lines.append(" ".join(cur))
    return lines


def bullet_list(items: list, bullet_color: str, font_size: int,
                max_chars: int = 40, row_buff: float = 0.38) -> VGroup:
    rows = []
    for item in items:
        parts = wrap_lines(item, max_chars=max_chars)
        first = True
        for line in parts:
            b = Text("•" if first else " ", font_size=font_size, color=bullet_color)
            t = Text(line, font_size=font_size, color=COLORS["text_body"])
            rows.append(VGroup(b, t).arrange(RIGHT, buff=0.25))
            first = False
    g = VGroup(*rows)
    g.arrange(DOWN, buff=row_buff, aligned_edge=LEFT)
    return g


def make_callout(text_str: str, stroke_color: str, fill_color: str,
                 width: float = 14.6, height: float = 0.95) -> VGroup:
    bg = RoundedRectangle(
        width=width, height=height, corner_radius=0.1,
        fill_color=fill_color, fill_opacity=1.0,
        stroke_color=stroke_color, stroke_width=1.5,
    )
    t = Text(text_str, font_size=FONTS["body_text"],
             color=COLORS["text_dark"], weight=BOLD)
    t.move_to(bg.get_center())
    g = VGroup(bg, t)
    g.to_edge(DOWN, buff=SPACING["page_bottom"])
    return g


def fade_out_all(scene, mobs):
    scene.play(FadeOut(VGroup(*mobs)), run_time=TIMING["transition"])


def resolve_color(color_key: str) -> str:
    """Resolve a color key like 'blue' to its hex value."""
    return COLORS.get(color_key, color_key)


def animate_callout(scene, text_str: str):
    """Animate a callout bar at the bottom if text is non-empty."""
    if not text_str:
        return None
    co = make_callout(text_str, stroke_color=COLORS["orange"],
                      fill_color=COLORS["highlight"])
    scene.play(Create(co[0]), FadeIn(co[1]), run_time=TIMING["group_fade"])
    return co
