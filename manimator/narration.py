"""Auto-generate narration scripts and TTS audio per scene."""

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import edge_tts

log = logging.getLogger(__name__)


# Map scene types to narration templates
def generate_narration_script(scene_data: dict) -> str:
    """Generate a narration script from scene data."""
    stype = scene_data["type"]

    if stype == "title":
        parts = [scene_data["title"]]
        if scene_data.get("subtitle"):
            parts.append(scene_data["subtitle"])
        return ". ".join(parts) + "."

    if stype == "bullet_list":
        header = scene_data["header"].split(". ", 1)[-1] if ". " in scene_data["header"] else scene_data["header"]
        items = scene_data["items"]
        script = f"{header}. "
        script += " ".join(items)
        if scene_data.get("callout"):
            script += f" {scene_data['callout']}"
        return script

    if stype == "two_panel":
        script = f"{scene_data['header'].split('. ', 1)[-1]}. "
        script += f"On one hand, {scene_data['left_title']}: "
        script += ". ".join(scene_data["left_items"]) + ". "
        script += f"On the other hand, {scene_data['right_title']}: "
        script += ". ".join(scene_data["right_items"]) + "."
        return script

    if stype == "comparison_table":
        header = scene_data["header"].split(". ", 1)[-1]
        cols = scene_data["columns"]
        rows = scene_data["rows"]
        script = f"Let's compare {header}. "
        for row in rows[:3]:  # Limit to avoid overly long narration
            script += f"For {row[0]}: "
            for j, val in enumerate(row[1:], 1):
                script += f"{cols[j]} is {val}. "
        return script

    if stype == "flowchart":
        header = scene_data["header"].split(". ", 1)[-1]
        stages = [s["label"].replace("\n", " ") for s in scene_data["stages"]]
        script = f"{header}. The process flows through: "
        script += ", then ".join(stages) + "."
        if scene_data.get("callout"):
            script += f" {scene_data['callout']}"
        return script

    if stype == "bar_chart":
        header = scene_data["header"].split(". ", 1)[-1]
        bars = scene_data["bars"]
        suffix = scene_data.get("value_suffix", "")
        script = f"{header}. "
        for b in bars:
            script += f"{b['label'].replace(chr(10), ' ')} at {b['value']}{suffix}. "
        if scene_data.get("callout"):
            script += scene_data["callout"]
        return script

    if stype == "scatter_plot":
        header = scene_data["header"].split(". ", 1)[-1]
        clusters = scene_data["clusters"]
        script = f"{header}. We see {len(clusters)} clusters: "
        script += ", ".join(c["label"] for c in clusters) + ". "
        if scene_data.get("callout"):
            script += scene_data["callout"]
        return script

    if stype == "equation":
        header = scene_data["header"].split(". ", 1)[-1]
        script = f"{header}. "
        if scene_data.get("explanation"):
            script += scene_data["explanation"]
        if scene_data.get("callout"):
            script += f" {scene_data['callout']}"
        return script

    if stype == "pipeline_diagram":
        header = scene_data["header"].split(". ", 1)[-1]
        cb = scene_data["center_block"]
        script = f"{header}. "
        script += f"The {cb['label']} integrates "
        script += f"{scene_data['left_track']['label']} and {scene_data['right_track']['label']}. "
        if cb.get("items"):
            script += "Key steps include: " + ", ".join(cb["items"][:4]) + ". "
        if scene_data.get("callout"):
            script += scene_data["callout"]
        return script

    if stype == "closing":
        refs = scene_data.get("references", [])
        if refs:
            return f"This presentation drew from {len(refs)} key references in the literature."
        return "Thank you for watching."

    return ""


# ── Chunk-based narration for per-element sync ──────────────────────────────


def generate_narration_chunks(scene_data: dict) -> list[str]:
    """Split a scene's narration into per-element chunks.

    For scene types with discrete visual elements (bullets, bars, stages, etc.),
    each element gets its own chunk so that TTS timing can drive CSS delays.
    When ``narration_text`` is set on the scene, that text is used as a
    single chunk instead of auto-generating.

    Returns a list of text chunks. Each chunk maps to one visual element
    in order: [header, element_1, element_2, ..., callout (if present)].
    """
    # Honour explicit narration_text override
    if scene_data.get("narration_text"):
        return [scene_data["narration_text"]]

    stype = scene_data.get("type", "")

    def _header(field: str = "header") -> str:
        raw = scene_data.get(field, "")
        return raw.split(". ", 1)[-1] if ". " in raw else raw

    if stype == "bullet_list":
        chunks = [_header()]
        chunks.extend(scene_data.get("items", []))
        if scene_data.get("callout"):
            chunks.append(scene_data["callout"])
        return chunks

    if stype == "flowchart":
        chunks = [_header()]
        for s in scene_data.get("stages", []):
            chunks.append(s["label"].replace("\n", " "))
        if scene_data.get("callout"):
            chunks.append(scene_data["callout"])
        return chunks

    if stype == "bar_chart":
        suffix = scene_data.get("value_suffix", "")
        chunks = [_header()]
        for b in scene_data.get("bars", []):
            chunks.append(f"{b['label'].replace(chr(10), ' ')} at {b['value']}{suffix}")
        if scene_data.get("callout"):
            chunks.append(scene_data["callout"])
        return chunks

    if stype == "comparison_table":
        cols = scene_data.get("columns", [])
        chunks = [f"Let's compare {_header()}"]
        for row in scene_data.get("rows", [])[:6]:
            parts = [f"For {row[0]}:"]
            for j, val in enumerate(row[1:], 1):
                if j < len(cols):
                    parts.append(f"{cols[j]} is {val}")
            chunks.append(". ".join(parts) + ".")
        if scene_data.get("callout"):
            chunks.append(scene_data["callout"])
        return chunks

    if stype == "scatter_plot":
        clusters = scene_data.get("clusters", [])
        chunks = [f"{_header()}. We see {len(clusters)} clusters"]
        for cl in clusters:
            chunks.append(cl["label"])
        if scene_data.get("callout"):
            chunks.append(scene_data["callout"])
        return chunks

    # All other scene types: single chunk (full narration text)
    full = generate_narration_script(scene_data)
    return [full] if full else []


def _merge_short_chunks(chunks: list[str], min_words: int = 3) -> list[str]:
    """Merge chunks shorter than *min_words* with their neighbor.

    Very short chunks produce unnatural TTS pauses. This merges them
    with the following chunk (or preceding, if last).
    """
    if len(chunks) <= 1:
        return chunks

    merged: list[str] = []
    carry = ""
    for chunk in chunks:
        combined = f"{carry} {chunk}".strip() if carry else chunk
        if len(combined.split()) < min_words:
            carry = combined
        else:
            merged.append(combined)
            carry = ""

    # Leftover carry attaches to last entry
    if carry:
        if merged:
            merged[-1] = f"{merged[-1]} {carry}"
        else:
            merged.append(carry)

    return merged


def synthesize_chunks(chunks: list[str], output_dir: Path,
                      scene_id: str, voice: str = "en-US-AriaNeural",
                      rate: str = "-5%") -> list[tuple[Path, float]]:
    """Synthesize each chunk to a separate MP3 and return (path, duration) pairs.

    Short chunks (<3 words) are merged with neighbors before synthesis
    to avoid choppy TTS output.
    """
    merged = _merge_short_chunks(chunks)
    results: list[tuple[Path, float]] = []

    for i, text in enumerate(merged):
        out_path = output_dir / f"{scene_id}_chunk{i:02d}.mp3"
        synthesize_audio(text, out_path, voice=voice, rate=rate)
        dur = get_audio_duration(out_path)
        results.append((out_path, dur))

    return results


def concatenate_audio_chunks(chunk_paths: list[Path],
                             output_path: Path) -> Path:
    """Join audio chunks into a single file via ffmpeg concat demuxer."""
    if len(chunk_paths) == 1:
        import shutil
        shutil.copy2(chunk_paths[0], output_path)
        return output_path

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as f:
        for p in chunk_paths:
            f.write(f"file '{p.resolve()}'\n")
        list_file = f.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c:a", "libmp3lame", "-q:a", "4",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Chunk concat failed:\n{result.stderr}")
    finally:
        import os
        os.unlink(list_file)

    return output_path


def compute_element_delays(chunk_durations: list[float],
                           lead_time: float = 0.15) -> list[float]:
    """Compute CSS animation delays from chunk durations.

    Element *i* appears at ``sum(durations[0:i]) + lead_time``.
    The lead time ensures the visual element appears slightly *before*
    the narrator says it (temporal contiguity principle — Mayer, 2009).

    Returns a list of delay values in seconds, one per chunk.
    """
    delays: list[float] = []
    cumulative = 0.0
    for i, dur in enumerate(chunk_durations):
        delays.append(max(cumulative + lead_time, 0.0) if i > 0 else lead_time)
        cumulative += dur
    return delays


async def _synthesize_edge(text: str, output_path: str,
                           voice: str = "en-US-AriaNeural",
                           rate: str = "-5%"):
    """Synthesize speech using edge-tts (30s timeout)."""
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await asyncio.wait_for(communicate.save(output_path), timeout=30)


def _synthesize_gtts(text: str, output_path: str):
    """Fallback: synthesize speech using gTTS (Google)."""
    from gtts import gTTS
    tts = gTTS(text, lang="en", slow=False)
    tts.save(output_path)


def sanitize_text(text: str) -> str:
    """Clean text for TTS — remove special chars that cause failures."""
    # Replace problematic characters
    replacements = {
        "θ": "theta", "η": "eta", "∇": "gradient of",
        "β": "beta", "ε": "epsilon", "α": "alpha",
        "χ": "chi", "μ": "mu", "σ": "sigma",
        "→": "to", "←": "from", "↓": "down", "↑": "up",
        "≥": "greater than or equal to", "≤": "less than or equal to",
        "×": "times", "÷": "divided by",
        "−": "minus", "–": "to", "—": ", ",
        "'": "'", "'": "'", """: '"', """: '"',
        "₁": "1", "₂": "2", "₃": "3", "₄": "4",
        "√": "square root of",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Remove any remaining non-ASCII that might cause issues
    text = text.encode("ascii", errors="ignore").decode("ascii")
    # Collapse multiple spaces
    text = " ".join(text.split())
    return text.strip()


def synthesize_audio(text: str, output_path: Path,
                     voice: str = "en-US-AriaNeural",
                     rate: str = "-5%"):
    """Blocking wrapper for TTS synthesis."""
    clean = sanitize_text(text)
    if not clean:
        clean = "Content continues."
    # Truncate very long text to avoid TTS failures
    if len(clean) > 2000:
        clean = clean[:2000].rsplit(" ", 1)[0] + "."
    # Try edge-tts first, fall back to gTTS
    try:
        asyncio.run(_synthesize_edge(clean, str(output_path), voice, rate))
    except Exception:
        _synthesize_gtts(clean, str(output_path))


def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def merge_audio_video(video_path: Path, audio_path: Path,
                      output_path: Path):
    """Merge audio and video, extending video if audio is longer."""
    video_dur = get_audio_duration(video_path)
    audio_dur = get_audio_duration(audio_path)

    if audio_dur > video_dur:
        # Extend video with last frame to match audio
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-filter_complex",
            f"[0:v]tpad=stop_mode=clone:stop_duration={audio_dur - video_dur + 0.5}[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libvpx-vp9", "-c:a", "libopus",
            "-shortest",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "libopus",
            "-shortest",
            str(output_path),
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio merge failed:\n{result.stderr}")


# Available voices for selection
VOICES = {
    "aria": "en-US-AriaNeural",        # Female, professional
    "guy": "en-US-GuyNeural",          # Male, professional
    "jenny": "en-US-JennyNeural",      # Female, warm
    "davis": "en-US-DavisNeural",      # Male, conversational
    "andrew": "en-US-AndrewNeural",    # Male, authoritative
    "emma": "en-US-EmmaNeural",        # Female, clear
}
