from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import create_section_header, fade_out_all, animate_callout


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    columns = data["columns"]
    rows = data["rows"]
    n_cols = len(columns)
    n_rows = len(rows) + 1  # +1 for header

    # Auto-calculate column widths if not provided
    col_widths = data.get("col_widths")
    if not col_widths:
        total_w = 16.0
        col_widths = [total_w / n_cols] * n_cols

    cell_h = 0.65
    all_data = [columns] + rows
    table = VGroup()

    for i, row in enumerate(all_data):
        is_header = i == 0
        for j, cell_text in enumerate(row):
            w = col_widths[j]
            cell = RoundedRectangle(
                width=w, height=cell_h, corner_radius=0.04,
                fill_color=(COLORS["blue"] if is_header else COLORS["bg_card"]),
                fill_opacity=(0.18 if is_header else 1.0),
                stroke_color=COLORS["border"],
                stroke_width=(1.2 if is_header else 1.0),
            )
            x = sum(col_widths[:j]) - sum(col_widths) / 2 + w / 2
            y = (n_rows / 2 - i - 0.5) * cell_h
            cell.move_to(RIGHT * x + DOWN * y)

            txt = Text(
                str(cell_text),
                font_size=(FONTS["table_header"] if is_header else FONTS["table_cell"]),
                color=(COLORS["text_dark"] if is_header else COLORS["text_body"]),
                weight=(BOLD if is_header else NORMAL),
            )
            txt.move_to(cell.get_center())
            table.add(cell, txt)

    table.move_to(ORIGIN + DOWN * 0.3)
    mobs = [header, table]

    scene.play(
        LaggedStart(*[FadeIn(mob, scale=0.95) for mob in table], lag_ratio=0.01),
        run_time=1.2
    )

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)
