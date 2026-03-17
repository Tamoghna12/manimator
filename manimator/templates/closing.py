from manim import *
from manimator.config import COLORS, TIMING, FONTS
from manimator.helpers import fade_out_all

# ── Constants ──────────────────────────────────────────────────────────────
MAX_PER_PAGE   = 6      # refs per "page" before paginating
ENTRY_FONT     = 16
NUM_FONT       = 15
DOI_FONT       = 13
LINE_BUFF      = 0.38
RULE_COLOR     = "#4477AA"   # Tol blue, consistent with chart palette
RULE_WIDTH     = 3.0
MAX_LINE_WIDTH = 11.5        # scene units before wrapping


def _build_entry(i: int, ref: dict | str) -> VGroup:
    """
    Accepts either a plain string (legacy) or a structured dict:
      {
        "authors": "Smith J, Doe A",
        "year":    "2024",
        "title":   "Deep learning for enzyme kinetics",
        "journal": "Nature Methods",
        "volume":  "21",
        "pages":   "123–134",
        "doi":     "10.1038/s41592-024-0001-x"   # optional
      }
    """
    # ── Number badge ────────────────────────────────────────────────────
    num_box = RoundedRectangle(
        corner_radius=0.08,
        width=0.52, height=0.36,
        fill_color=RULE_COLOR, fill_opacity=0.18,
        stroke_color=RULE_COLOR, stroke_width=1.2,
    )
    num_label = Text(
        f"{i + 1}", font_size=NUM_FONT,
        color=RULE_COLOR, weight=BOLD,
    ).move_to(num_box)
    badge = VGroup(num_box, num_label)

    # ── Reference body ───────────────────────────────────────────────────
    if isinstance(ref, str):
        # Legacy plain-string path
        body_text = MarkupText(
            ref, font_size=ENTRY_FONT,
            color=COLORS["text_body"],
        )
        body_text.width = min(body_text.width, MAX_LINE_WIDTH)
        body = VGroup(body_text)

    else:
        authors  = ref.get("authors", "")
        year     = ref.get("year", "")
        title    = ref.get("title", "")
        journal  = ref.get("journal", "")
        volume   = ref.get("volume", "")
        pages    = ref.get("pages", "")
        doi      = ref.get("doi", "")

        # Line 1: Authors (year).  Title.
        line1_str = (
            f'<span foreground="{COLORS["text_dark"]}">'
            f'<b>{authors}</b></span>'
            f' <span foreground="{COLORS["text_muted"]}">({year})</span>.'
            f'  {title}.'
        )
        line1 = MarkupText(line1_str, font_size=ENTRY_FONT)
        line1.width = min(line1.width, MAX_LINE_WIDTH)

        # Line 2: Journal volume, pages.
        journal_str = (
            f'<i><span foreground="{COLORS["blue"]}">{journal}</span></i>'
            + (f', <b>{volume}</b>' if volume else "")
            + (f', {pages}' if pages else "")
            + "."
        )
        line2 = MarkupText(journal_str, font_size=ENTRY_FONT)

        body_parts = [line1, line2]

        # Line 3: DOI pill (optional)
        if doi:
            doi_bg = RoundedRectangle(
                corner_radius=0.07,
                fill_color=COLORS.get("surface_alt", "#1E1E2E"),
                fill_opacity=0.9,
                stroke_color=COLORS["text_muted"],
                stroke_width=0.6,
                height=0.28,
            )
            doi_label = MarkupText(
                f'<span foreground="{COLORS["text_muted"]}">doi: </span>'
                f'<span foreground="{RULE_COLOR}">{doi}</span>',
                font_size=DOI_FONT,
            )
            doi_bg.width = doi_label.width + 0.3
            doi_label.move_to(doi_bg)
            doi_pill = VGroup(doi_bg, doi_label)
            body_parts.append(doi_pill)

        body = VGroup(*body_parts)
        body.arrange(DOWN, buff=0.10, aligned_edge=LEFT)

    # ── Left accent rule ────────────────────────────────────────────────
    rule = Line(
        UP * body.height / 2,
        DOWN * body.height / 2,
        color=RULE_COLOR,
        stroke_width=RULE_WIDTH,
    )

    row = VGroup(badge, rule, body)
    row.arrange(RIGHT, buff=0.22, aligned_edge=UP)
    return row


def _paginate(refs: list, per_page: int) -> list[list]:
    return [refs[i: i + per_page] for i in range(0, len(refs), per_page)]


def render(scene: Scene, data: dict):
    # ── Title ────────────────────────────────────────────────────────────
    title = Text(
        data.get("title", "References"),
        font_size=FONTS["scene_title"],
        color=COLORS["text_dark"],
        weight=BOLD,
    )
    title.to_edge(UP, buff=0.7)
    scene.play(FadeIn(title), run_time=0.4)

    refs   = data.get("references", [])
    pages  = _paginate(refs, MAX_PER_PAGE)
    mobs   = [title]

    for p_idx, page_refs in enumerate(pages):

        # ── Page indicator (e.g. "1 / 2") for multi-page lists ──────────
        page_indicator = VMobject()
        if len(pages) > 1:
            page_indicator = Text(
                f"{p_idx + 1} / {len(pages)}",
                font_size=13,
                color=COLORS["text_muted"],
            ).to_corner(DR, buff=0.4)
            scene.play(FadeIn(page_indicator), run_time=0.2)
            mobs.append(page_indicator)

        # ── Build entry rows ─────────────────────────────────────────────
        entries = VGroup(*[_build_entry(
            p_idx * MAX_PER_PAGE + j, ref
        ) for j, ref in enumerate(page_refs)])

        entries.arrange(DOWN, buff=LINE_BUFF, aligned_edge=LEFT)
        entries.move_to(ORIGIN + DOWN * 0.2)

        # Keep within frame vertically
        if entries.get_top()[1] > title.get_bottom()[1] - 0.2:
            entries.next_to(title, DOWN, buff=0.35)

        mobs.append(entries)

        # ── Animate: rules draw first, then text fades in ────────────────
        rules  = VGroup(*[e[1] for e in entries])   # index 1 = rule
        bodies = [VGroup(e[0], e[2]) for e in entries]  # badge + body

        scene.play(
            LaggedStart(
                *[Create(r) for r in rules],
                lag_ratio=0.10,
            ),
            run_time=0.5,
        )
        scene.play(
            LaggedStart(
                *[FadeIn(b, shift=RIGHT * 0.12) for b in bodies],
                lag_ratio=0.13,
            ),
            run_time=max(0.8, len(page_refs) * 0.15),
        )

        hold = data.get("hold_time", TIMING.get("scene_pause", 3.0))
        scene.wait(hold)

        # Transition between pages
        if p_idx < len(pages) - 1:
            scene.play(FadeOut(entries), FadeOut(page_indicator), run_time=0.4)
            mobs.remove(entries)
            mobs.remove(page_indicator)

    fade_out_all(scene, mobs)

