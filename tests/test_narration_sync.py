"""Tests for narration chunk splitting, element delay computation, and SceneTiming."""

import pytest

from manimator.narration import (
    generate_narration_chunks,
    compute_element_delays,
    _merge_short_chunks,
)
from manimator.timing import SceneTiming


# ── generate_narration_chunks ─────────────────────────────────────────────────


class TestGenerateNarrationChunks:
    def test_bullet_list_produces_header_plus_items(self):
        data = {
            "type": "bullet_list",
            "header": "Key Points",
            "items": ["Alpha", "Beta", "Gamma"],
            "callout": "Important note",
        }
        chunks = generate_narration_chunks(data)
        # header + 3 items + callout = 5
        assert len(chunks) == 5
        assert chunks[0] == "Key Points"
        assert chunks[1] == "Alpha"
        assert chunks[-1] == "Important note"

    def test_bullet_list_no_callout(self):
        data = {
            "type": "bullet_list",
            "header": "Points",
            "items": ["A", "B"],
        }
        chunks = generate_narration_chunks(data)
        assert len(chunks) == 3  # header + 2 items

    def test_flowchart_produces_header_plus_stages(self):
        data = {
            "type": "flowchart",
            "header": "01. Pipeline",
            "stages": [
                {"label": "Step One"},
                {"label": "Step Two"},
            ],
            "callout": "Note",
        }
        chunks = generate_narration_chunks(data)
        assert len(chunks) == 4  # header + 2 stages + callout
        assert chunks[0] == "Pipeline"  # strips "01. " prefix
        assert chunks[1] == "Step One"

    def test_bar_chart_produces_header_plus_bars(self):
        data = {
            "type": "bar_chart",
            "header": "03. Results",
            "bars": [
                {"label": "X", "value": 10},
                {"label": "Y", "value": 20},
            ],
            "value_suffix": "%",
        }
        chunks = generate_narration_chunks(data)
        assert len(chunks) == 3  # header + 2 bars
        assert "10%" in chunks[1]
        assert "20%" in chunks[2]

    def test_comparison_table_produces_header_plus_rows(self):
        data = {
            "type": "comparison_table",
            "header": "Comparison",
            "columns": ["Method", "Speed", "Cost"],
            "rows": [
                ["A", "Fast", "$10"],
                ["B", "Slow", "$5"],
            ],
            "callout": "Takeaway",
        }
        chunks = generate_narration_chunks(data)
        assert len(chunks) == 4  # header + 2 rows + callout

    def test_scatter_plot_produces_header_plus_clusters(self):
        data = {
            "type": "scatter_plot",
            "header": "Clusters",
            "clusters": [
                {"label": "Group A", "center": [1, 2]},
                {"label": "Group B", "center": [3, 4]},
            ],
            "axes": ["X", "Y"],
            "callout": "Notice the separation",
        }
        chunks = generate_narration_chunks(data)
        assert len(chunks) == 4  # header + 2 clusters + callout

    def test_title_scene_single_chunk(self):
        data = {
            "type": "title",
            "title": "My Title",
            "subtitle": "A subtitle",
        }
        chunks = generate_narration_chunks(data)
        assert len(chunks) == 1
        assert "My Title" in chunks[0]

    def test_narration_text_override(self):
        data = {
            "type": "bullet_list",
            "header": "Points",
            "items": ["A", "B", "C"],
            "narration_text": "Custom narration for this scene.",
        }
        chunks = generate_narration_chunks(data)
        assert len(chunks) == 1
        assert chunks[0] == "Custom narration for this scene."

    def test_empty_scene_returns_empty(self):
        data = {"type": "unknown_type_xyz"}
        chunks = generate_narration_chunks(data)
        assert chunks == []


# ── _merge_short_chunks ───────────────────────────────────────────────────────


class TestMergeShortChunks:
    def test_no_merge_needed(self):
        chunks = ["This is long enough", "Another long one here"]
        assert _merge_short_chunks(chunks) == chunks

    def test_short_chunk_merged_forward(self):
        chunks = ["Hi", "This is a longer sentence"]
        merged = _merge_short_chunks(chunks, min_words=3)
        assert len(merged) == 1
        assert "Hi" in merged[0]
        assert "longer" in merged[0]

    def test_single_chunk_unchanged(self):
        assert _merge_short_chunks(["OK"]) == ["OK"]

    def test_empty_list(self):
        assert _merge_short_chunks([]) == []

    def test_trailing_short_chunk(self):
        chunks = ["A full sentence here", "OK"]
        merged = _merge_short_chunks(chunks, min_words=3)
        assert len(merged) == 1
        assert "OK" in merged[0]


# ── compute_element_delays ────────────────────────────────────────────────────


class TestComputeElementDelays:
    def test_basic_delays(self):
        durations = [2.0, 1.5, 3.0]
        delays = compute_element_delays(durations, lead_time=0.15)
        assert len(delays) == 3
        # First element: lead_time
        assert delays[0] == pytest.approx(0.15)
        # Second element: sum(durations[0:1]) + lead_time = 2.0 + 0.15
        assert delays[1] == pytest.approx(2.15)
        # Third element: sum(durations[0:2]) + lead_time = 3.5 + 0.15
        assert delays[2] == pytest.approx(3.65)

    def test_single_chunk(self):
        delays = compute_element_delays([5.0])
        assert len(delays) == 1
        assert delays[0] == pytest.approx(0.15)

    def test_custom_lead_time(self):
        delays = compute_element_delays([1.0, 1.0], lead_time=0.5)
        assert delays[0] == pytest.approx(0.5)
        assert delays[1] == pytest.approx(1.5)

    def test_empty_durations(self):
        assert compute_element_delays([]) == []


# ── SceneTiming ───────────────────────────────────────────────────────────────


class TestSceneTiming:
    def test_defaults(self):
        t = SceneTiming(total_duration=5.0)
        assert t.total_duration == 5.0
        assert t.element_delays is None
        assert t.header_delay == 0.2

    def test_with_delays(self):
        t = SceneTiming(
            total_duration=10.0,
            element_delays=[0.15, 2.15, 4.0],
            header_delay=0.1,
        )
        assert len(t.element_delays) == 3
        assert t.header_delay == 0.1
