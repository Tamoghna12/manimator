import numpy as np
from scipy.spatial import ConvexHull
from manim import *
from manimator.config import COLORS, TIMING, FONTS, SPACING
from manimator.helpers import (
    create_section_header, make_card, fade_out_all,
    animate_callout, resolve_color,
)

# ── Palette cycling (Tol colorblind-safe) ─────────────────────────────────
SCI_PALETTE = [
    "#4477AA", "#EE6677", "#228833", "#CCBB44",
    "#66CCEE", "#AA3377", "#EE8866", "#44BB99",
]

# ── Dot shape factories (vary marker per cluster for accessibility) ────────
def _dot_factory(shape: str, color: str, radius: float = 0.09) -> VMobject:
    """
    Returns a marker mobject.
    shape ∈ {"circle", "square", "triangle", "diamond", "cross"}
    """
    s = shape.lower()
    if s == "square":
        m = Square(side_length=radius * 2.0,
                   fill_color=color, fill_opacity=0.85,
                   stroke_width=0.4, stroke_color=color)
    elif s == "triangle":
        m = Triangle(fill_color=color, fill_opacity=0.85,
                     stroke_width=0.4, stroke_color=color)
        m.scale(radius * 1.4)
    elif s == "diamond":
        m = Square(side_length=radius * 1.8,
                   fill_color=color, fill_opacity=0.85,
                   stroke_width=0.4, stroke_color=color).rotate(PI / 4)
    elif s == "cross":
        h = Line(LEFT * radius, RIGHT * radius,
                 stroke_width=2.5, color=color)
        v = Line(DOWN * radius, UP   * radius,
                 stroke_width=2.5, color=color)
        m = VGroup(h, v)
    else:
        m = Dot(radius=radius, color=color, fill_opacity=0.85,
                stroke_width=0.4, stroke_color=color)
    return m


def _confidence_ellipse(
    xs: np.ndarray, ys: np.ndarray,
    color: str,
    n_std: float = 2.0,
    axes: Axes = None,
) -> Ellipse:
    """
    Draws the n_std-sigma covariance ellipse in data coords,
    mapped through the Axes object.
    """
    cov   = np.cov(xs, ys)
    vals, vecs = np.linalg.eigh(cov)
    order = vals.argsort()[::-1]
    vals, vecs = vals[order], vecs[:, order]

    angle_rad = np.arctan2(*vecs[:, 0][::-1])
    w, h = 2 * n_std * np.sqrt(vals)

    # Convert ellipse axes from data units → scene units
    cx_s, cy_s = axes.c2p(np.mean(xs), np.mean(ys))
    # Use a reference point to get scale factor
    ref_x = axes.c2p(np.mean(xs) + 1, np.mean(ys))
    ref_y = axes.c2p(np.mean(xs), np.mean(ys) + 1)
    sx = abs(ref_x[0] - cx_s)   # scene units per data unit, x
    sy = abs(ref_y[1] - cy_s)   # scene units per data unit, y

    ellipse = Ellipse(
        width=w * sx * 2,
        height=h * sy * 2,
        color=color,
        fill_opacity=0.08,
        stroke_width=1.2,
        stroke_opacity=0.7,
    )
    ellipse.move_to([cx_s, cy_s, 0])
    ellipse.rotate(angle_rad)
    return ellipse


def _convex_hull_poly(
    xs: np.ndarray, ys: np.ndarray,
    color: str, axes: Axes,
) -> VMobject | None:
    """Convex hull boundary polygon in scene space."""
    pts = np.column_stack([xs, ys])
    if len(pts) < 3:
        return None
    try:
        hull = ConvexHull(pts)
    except Exception:
        return None
    hull_pts = pts[hull.vertices]
    scene_pts = [axes.c2p(x, y) for x, y in hull_pts]
    poly = Polygon(*scene_pts,
                   color=color,
                   fill_opacity=0.06,
                   stroke_width=1.0,
                   stroke_opacity=0.5)
    return poly


def _centroid_crosshair(cx: float, cy: float,
                         color: str, axes: Axes,
                         arm: float = 0.18) -> VGroup:
    """Small + crosshair at the cluster centroid in scene space."""
    pt  = axes.c2p(cx, cy)
    h   = Line([pt[0] - arm, pt[1], 0], [pt[0] + arm, pt[1], 0],
               stroke_width=1.6, color=color)
    v   = Line([pt[0], pt[1] - arm, 0], [pt[0], pt[1] + arm, 0],
               stroke_width=1.6, color=color)
    rim = Circle(radius=arm * 0.55, color=color,
                 stroke_width=1.0, stroke_opacity=0.6)
    rim.move_to(pt)
    return VGroup(h, v, rim)


def _axis_labels_latex(
    axes: Axes, x_str: str, y_str: str
) -> tuple[MathTex, MathTex]:
    """LaTeX axis labels with automatic fallback to Text."""
    try:
        x_lab = MathTex(x_str, font_size=18,
                         color=COLORS["text_muted"])
    except Exception:
        x_lab = Text(x_str, font_size=16, color=COLORS["text_muted"])
    x_lab.next_to(axes, DOWN, buff=0.35)

    try:
        y_lab = MathTex(y_str, font_size=18,
                         color=COLORS["text_muted"])
    except Exception:
        y_lab = Text(y_str, font_size=16, color=COLORS["text_muted"])
    y_lab.next_to(axes, LEFT, buff=0.35).rotate(PI / 2)
    return x_lab, y_lab


MARKER_SHAPES = ["circle", "square", "triangle", "diamond", "cross"]


def render(scene: Scene, data: dict):
    header = create_section_header(data["header"])
    scene.play(FadeIn(header), run_time=TIMING["element_fade"])

    axes_labels = data.get("axes", ["x", "y"])
    clusters    = data["clusters"]

    # ── Dynamic axis range ─────────────────────────────────────────────
    all_centers = [c["center"] for c in clusters]
    spreads     = [c.get("spread", 0.6) * 3 for c in clusters]
    xs_c = [p[0] for p in all_centers]
    ys_c = [p[1] for p in all_centers]
    pad  = max(spreads) + 0.8
    x_min, x_max = np.floor(min(xs_c) - pad), np.ceil(max(xs_c) + pad)
    y_min, y_max = np.floor(min(ys_c) - pad), np.ceil(max(ys_c) + pad)
    x_step = max(1, round((x_max - x_min) / 8))
    y_step = max(1, round((y_max - y_min) / 6))

    axes = Axes(
        x_range=[x_min, x_max, x_step],
        y_range=[y_min, y_max, y_step],
        x_length=9.5,
        y_length=6.0,
        axis_config={
            "color":        COLORS["text_muted"],
            "stroke_width": 1.4,
            "include_numbers": True,
            "font_size":    14,
            "decimal_number_config": {"num_decimal_places": 0,
                                      "color": COLORS["text_muted"]},
        },
        tips=True,
    )

    x_lab, y_lab = _axis_labels_latex(axes, axes_labels[0], axes_labels[1])
    axes_group = VGroup(axes, x_lab, y_lab)
    axes_group.move_to(LEFT * 2.2 + DOWN * 0.3)

    # ── Grid (subtle dotted) ──────────────────────────────────────────
    grid = NumberPlane(
        x_range=[x_min, x_max, x_step],
        y_range=[y_min, y_max, y_step],
        x_length=9.5,
        y_length=6.0,
        background_line_style={
            "stroke_color":   COLORS["text_muted"],
            "stroke_width":   0.4,
            "stroke_opacity": 0.25,
        },
        faded_line_ratio=0,
    ).move_to(axes.get_center())

    np.random.seed(data.get("seed", 42))

    all_dot_groups   = []   # list of VGroup per cluster
    ellipse_groups   = []   # 1σ + 2σ per cluster
    hull_polys       = []
    crosshairs       = []
    legend_items     = VGroup()
    raw_coords       = []   # [(xs, ys)] per cluster

    for ci, cluster in enumerate(clusters):
        col   = cluster.get("color_key")
        col   = resolve_color(col) if col else SCI_PALETTE[ci % len(SCI_PALETTE)]
        cx, cy = cluster["center"]
        spread = cluster.get("spread", 0.5)
        n      = cluster.get("n", 25)
        shape  = cluster.get("shape", MARKER_SHAPES[ci % len(MARKER_SHAPES)])
        cov_xy = cluster.get("cov", [[spread**2, 0], [0, spread**2]])

        # Correlated 2D Gaussian
        mean  = np.array([cx, cy])
        cov_m = np.array(cov_xy)
        pts   = np.random.multivariate_normal(mean, cov_m, size=n)
        xs, ys = pts[:, 0], pts[:, 1]
        raw_coords.append((xs, ys))

        # ── Dots ──────────────────────────────────────────────────────
        dot_group = VGroup()
        for x, y in zip(xs, ys):
            marker = _dot_factory(shape, col, radius=0.085)
            marker.move_to(axes.c2p(x, y))
            dot_group.add(marker)
        all_dot_groups.append(dot_group)

        # ── Confidence ellipses (1σ dashed, 2σ solid) ─────────────────
        e1 = _confidence_ellipse(xs, ys, col, n_std=1.0, axes=axes)
        e1.set_stroke(opacity=0.45, width=1.0)
        e1.set_dash_pattern([0.07, 0.05])
        e2 = _confidence_ellipse(xs, ys, col, n_std=2.0, axes=axes)
        ellipse_groups.append(VGroup(e1, e2))

        # ── Convex hull (optional per cluster) ────────────────────────
        if cluster.get("show_hull", False):
            hp = _convex_hull_poly(xs, ys, col, axes)
            hull_polys.append(hp)
        else:
            hull_polys.append(None)

        # ── Centroid crosshair ─────────────────────────────────────────
        cross = _centroid_crosshair(float(np.mean(xs)), float(np.mean(ys)),
                                     col, axes)
        crosshairs.append(cross)

        # ── Legend row ────────────────────────────────────────────────
        leg_marker = _dot_factory(shape, col, radius=0.10)
        leg_label  = Text(cluster["label"],
                          font_size=14, color=COLORS["text_body"])
        n_ann      = MathTex(f"n={n}", font_size=12,
                              color=COLORS["text_muted"])
        leg_row    = VGroup(leg_marker, leg_label, n_ann).arrange(
            RIGHT, buff=0.18)
        legend_items.add(leg_row)

    # ── Legend panel ───────────────────────────────────────────────────
    legend_items.arrange(DOWN, buff=0.22, aligned_edge=LEFT)
    leg_bg = make_card(
        legend_items.width + 0.65,
        legend_items.height + 0.45,
        stroke_color=COLORS["border"],
    )
    legend_items.move_to(leg_bg)
    legend = VGroup(leg_bg, legend_items)
    legend.next_to(axes_group, RIGHT, buff=0.65).align_to(axes_group, UP)

    mobs = [header, axes_group, grid, legend,
            *[g for g in hull_polys if g],
            *ellipse_groups, *crosshairs,
            *all_dot_groups]

    # ── Animation sequence ─────────────────────────────────────────────
    # 1. Grid fades, then axes draw
    scene.play(FadeIn(grid), run_time=0.25)
    scene.play(Create(axes), FadeIn(x_lab), FadeIn(y_lab), run_time=0.55)

    # 2. Convex hulls grow from centroid (if any)
    for hp in hull_polys:
        if hp:
            scene.play(GrowFromCenter(hp), run_time=0.3)

    # 3. Confidence ellipses draw outward before dots appear
    for eg in ellipse_groups:
        scene.play(Create(eg[1]), Create(eg[0]), run_time=0.3)

    # 4. Dots spray in per cluster
    for dg in all_dot_groups:
        scene.play(
            LaggedStart(*[FadeIn(d, scale=0.4) for d in dg], lag_ratio=0.015),
            run_time=max(0.4, len(dg) * 0.015),
        )

    # 5. Crosshairs snap into place
    scene.play(
        LaggedStart(*[GrowFromCenter(c) for c in crosshairs], lag_ratio=0.12),
        run_time=0.4,
    )

    # 6. Legend slides in
    scene.play(FadeIn(legend, shift=LEFT * 0.2), run_time=0.35)

    co = animate_callout(scene, data.get("callout", ""))
    if co:
        mobs.append(co)

    scene.wait(TIMING["scene_pause"])
    fade_out_all(scene, mobs)

