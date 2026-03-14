"""Auto-generate narration scripts and TTS audio per scene."""

import asyncio
import subprocess
from pathlib import Path

import edge_tts


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


async def _synthesize_edge(text: str, output_path: str,
                           voice: str = "en-US-AriaNeural",
                           rate: str = "-5%"):
    """Synthesize speech using edge-tts."""
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_path)


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
