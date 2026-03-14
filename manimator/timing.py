"""Timing data structures for narration-synced scene rendering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SceneTiming:
    """Timing information derived from narration audio chunks.

    When provided to HTML renderers, element_delays override the
    hardcoded CSS animation delays so that visual elements appear
    in sync with the narrator's speech.
    """

    total_duration: float
    element_delays: list[float] | None = None
    header_delay: float = 0.2
