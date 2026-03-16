"""Pydantic v2 models for storyboard JSON validation."""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Branding(BaseModel):
    """Customisable branding & call-to-action shown on every video."""
    channel_name: str = ""            # e.g. "@ScienceExplained"
    cta_text: str = ""                # e.g. "Follow for more science!"
    accent_label: str = ""            # hook scene pill text (default "Watch This")
    social_handles: list[str] = []    # e.g. ["@sci_explained", "youtube.com/SciX"]
    watermark_text: str = ""          # persistent corner watermark
    logo_url: str = ""                # URL or path to logo image


class Meta(BaseModel):
    title: str
    author: str = "Auto-generated"
    resolution: tuple[int, int] = (1920, 1080)
    fps: int = 60
    output_format: Literal["webm", "mp4"] = "mp4"
    color_theme: str = "wong"
    format: str = "presentation"  # presentation, instagram_reel, linkedin, etc.
    pacing: str = ""              # auto, fast, medium, slow (empty = auto from format)
    background_music: Optional[str] = None  # preset name or file path
    branding: Optional[Branding] = None


# ── Scene types ─────────────────────────────────────────────────────────────

class HookScene(BaseModel):
    type: Literal["hook"] = "hook"
    id: str
    hook_text: str
    subtitle: str = ""
    narration_text: Optional[str] = None


class TitleScene(BaseModel):
    type: Literal["title"] = "title"
    id: str
    title: str
    subtitle: str = ""
    footnote: str = ""
    narration_text: Optional[str] = None


class BulletListScene(BaseModel):
    type: Literal["bullet_list"] = "bullet_list"
    id: str
    header: str
    items: list[str]
    callout: str = ""
    narration_text: Optional[str] = None


class TwoPanelScene(BaseModel):
    type: Literal["two_panel"] = "two_panel"
    id: str
    header: str
    left_title: str
    left_items: list[str]
    right_title: str
    right_items: list[str]
    callout: str = ""
    narration_text: Optional[str] = None


class ComparisonTableScene(BaseModel):
    type: Literal["comparison_table"] = "comparison_table"
    id: str
    header: str
    columns: list[str]
    rows: list[list[str]]
    col_widths: Optional[list[float]] = None
    callout: str = ""
    narration_text: Optional[str] = None


class FlowchartStage(BaseModel):
    label: str
    color_key: str = "blue"
    bg: str = "#E8F4FD"


class RecycleConfig(BaseModel):
    from_idx: int
    to_idx: int
    label: str = "Recycle"


class FlowchartScene(BaseModel):
    type: Literal["flowchart"] = "flowchart"
    id: str
    header: str
    stages: list[FlowchartStage]
    recycle: Optional[RecycleConfig] = None
    callout: str = ""
    narration_text: Optional[str] = None


class BarData(BaseModel):
    label: str
    value: float
    color_key: str = "blue"


class BarChartScene(BaseModel):
    type: Literal["bar_chart"] = "bar_chart"
    id: str
    header: str
    bars: list[BarData]
    value_suffix: str = ""
    callout: str = ""
    narration_text: Optional[str] = None


class ClusterData(BaseModel):
    label: str
    center: list[float] = Field(min_length=2, max_length=2)
    n: int = 20
    spread: float = 0.4
    color_key: str = "blue"


class ScatterPlotScene(BaseModel):
    type: Literal["scatter_plot"] = "scatter_plot"
    id: str
    header: str
    clusters: list[ClusterData]
    axes: list[str] = Field(min_length=2, max_length=2)
    callout: str = ""
    narration_text: Optional[str] = None


class TrackConfig(BaseModel):
    label: str
    color_key: str = "blue"
    sublabel: str = ""


class CenterBlockConfig(BaseModel):
    label: str
    color_key: str = "orange"
    items: list[str] = []


class PipelineDiagramScene(BaseModel):
    type: Literal["pipeline_diagram"] = "pipeline_diagram"
    id: str
    header: str
    left_track: TrackConfig
    right_track: TrackConfig
    center_block: CenterBlockConfig
    callout: str = ""
    narration_text: Optional[str] = None


class EquationScene(BaseModel):
    type: Literal["equation"] = "equation"
    id: str
    header: str
    latex: str
    explanation: str = ""
    callout: str = ""
    narration_text: Optional[str] = None


class ClosingScene(BaseModel):
    type: Literal["closing"] = "closing"
    id: str
    title: str = "Key References"
    references: list[str] = []
    cta_text: str = ""  # overrides meta.branding.cta_text for this scene
    narration_text: Optional[str] = None


# ── Discriminated union ─────────────────────────────────────────────────────

from typing import Annotated, Union
from pydantic import Discriminator, Tag

SceneSpec = Annotated[
    Union[
        Annotated[HookScene, Tag("hook")],
        Annotated[TitleScene, Tag("title")],
        Annotated[BulletListScene, Tag("bullet_list")],
        Annotated[TwoPanelScene, Tag("two_panel")],
        Annotated[ComparisonTableScene, Tag("comparison_table")],
        Annotated[FlowchartScene, Tag("flowchart")],
        Annotated[BarChartScene, Tag("bar_chart")],
        Annotated[ScatterPlotScene, Tag("scatter_plot")],
        Annotated[PipelineDiagramScene, Tag("pipeline_diagram")],
        Annotated[EquationScene, Tag("equation")],
        Annotated[ClosingScene, Tag("closing")],
    ],
    Discriminator("type"),
]


class Storyboard(BaseModel):
    meta: Meta
    scenes: list[SceneSpec]
