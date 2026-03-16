"""Frame-by-frame video capture using Playwright screenshots + ffmpeg.

Instead of Playwright's low-quality video recording, this renders
each animation frame as a high-resolution PNG screenshot, then encodes
them into video with ffmpeg at controlled bitrate and framerate.
Scene transitions (crossfade) are added at the ffmpeg level.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

log = logging.getLogger(__name__)

from playwright.sync_api import sync_playwright

if TYPE_CHECKING:
    from manimator.timing import SceneTiming


# ── Duration estimation ───────────────────────────────────────────────────────

def _get_minimum_animation_time(scene_data: dict) -> float:
    """Return the shortest time needed for all CSS animations to complete."""
    stype = scene_data.get("type", "")

    if stype == "hook":
        n_words = len(scene_data.get("hook_text", "").split())
        return 0.4 + n_words * 0.1 + 0.6
    elif stype == "title":
        return 2.0
    elif stype == "bullet_list":
        n = len(scene_data.get("items", []))
        return 0.7 + n * 0.25 + 0.6
    elif stype == "flowchart":
        n = len(scene_data.get("stages", []))
        return 0.5 + n * 0.35 + 0.6
    elif stype == "bar_chart":
        n = len(scene_data.get("bars", []))
        return 0.6 + n * 0.3 + 1.0 + 0.6
    elif stype == "two_panel":
        return 2.5
    elif stype == "comparison_table":
        n = len(scene_data.get("rows", []))
        return 0.7 + n * 0.2 + 0.6
    elif stype == "scatter_plot":
        n = len(scene_data.get("clusters", []))
        return 0.6 + n * 0.25 + 0.6
    elif stype == "equation":
        return 2.5
    elif stype == "pipeline_diagram":
        return 3.0
    elif stype == "closing":
        n = len(scene_data.get("references", []))
        return 0.9 + n * 0.2 + 0.6
    return 2.0


def _get_scene_duration(scene_data: dict,
                        audio_duration: float | None = None) -> float:
    """Estimate CSS animation duration for a scene type.

    When *audio_duration* is provided (narration-sync mode), the duration
    is ``max(audio_duration + 0.5, minimum_animation_time)`` so the video
    is long enough for both the narration and the CSS animations.
    """
    if audio_duration is not None:
        min_anim = _get_minimum_animation_time(scene_data)
        return max(audio_duration + 0.5, min_anim)

    stype = scene_data.get("type", "")

    if stype == "hook":
        n_words = len(scene_data.get("hook_text", "").split())
        return 0.4 + n_words * 0.1 + 1.8
    elif stype == "title":
        return 3.5
    elif stype == "bullet_list":
        n = len(scene_data.get("items", []))
        return 0.7 + n * 0.25 + 2.0
    elif stype == "flowchart":
        n = len(scene_data.get("stages", []))
        return 0.5 + n * 0.35 + 2.0
    elif stype == "bar_chart":
        n = len(scene_data.get("bars", []))
        return 0.6 + n * 0.3 + 1.0 + 2.0
    elif stype == "two_panel":
        return 4.0
    elif stype == "comparison_table":
        n = len(scene_data.get("rows", []))
        return 0.7 + n * 0.2 + 2.0
    elif stype == "scatter_plot":
        n = len(scene_data.get("clusters", []))
        return 0.6 + n * 0.25 + 2.0
    elif stype == "equation":
        return 4.0
    elif stype == "pipeline_diagram":
        return 4.5
    elif stype == "closing":
        n = len(scene_data.get("references", []))
        return 0.9 + n * 0.2 + 2.5

    return 3.5


# ── Frame-by-frame capture ───────────────────────────────────────────────────

def capture_scene_frames(html_path: Path, frames_dir: Path,
                         duration: float, width: int = 1080,
                         height: int = 1920, fps: int = 60) -> int:
    """Capture a scene as PNG frames using Playwright screenshots.

    Uses Web Animations API to precisely control animation timing,
    advancing animations frame-by-frame for perfectly smooth output
    regardless of capture speed.

    Returns the number of frames captured.
    """
    frames_dir.mkdir(parents=True, exist_ok=True)
    total_frames = int(duration * fps)
    frame_ms = 1000.0 / fps

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": width, "height": height})

        # Load page and immediately pause all animations
        page.goto(f"file://{html_path.resolve()}")
        page.wait_for_timeout(200)  # Let initial layout settle

        # Pause all CSS animations and set them to time 0
        page.evaluate("""
            document.getAnimations().forEach(a => {
                a.pause();
                a.currentTime = 0;
            });
        """)

        for frame_num in range(total_frames):
            # Set all animations to the exact time for this frame
            current_time_ms = frame_num * frame_ms
            page.evaluate(f"""
                document.getAnimations().forEach(a => {{
                    a.currentTime = {current_time_ms};
                }});
            """)

            # Also handle SVG <animate> elements via their timeline
            page.evaluate(f"""
                document.querySelectorAll('svg').forEach(svg => {{
                    if (svg.pauseAnimations) {{
                        svg.setCurrentTime({current_time_ms / 1000.0});
                    }}
                }});
            """)

            page.screenshot(
                path=str(frames_dir / f"frame_{frame_num:05d}.png"),
                type="png",
            )

        browser.close()

    return total_frames


def encode_frames_to_video(frames_dir: Path, output_path: Path,
                           fps: int = 60, crf: int = 18) -> Path:
    """Encode PNG frames into a high-quality WebM video."""
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%05d.png"),
        "-c:v", "libvpx-vp9",
        "-b:v", "0",           # CQ mode: let CRF drive quality, no bitrate cap
        "-crf", str(crf),
        "-quality", "good",
        "-speed", "4",
        "-row-mt", "1",        # Parallel row encoding
        "-pix_fmt", "yuva420p",
        "-an",                 # No audio yet
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Frame encoding failed:\n{result.stderr}")
    return output_path


def capture_scene(html_path: Path, output_path: Path,
                  duration: float, width: int = 1080,
                  height: int = 1920, fps: int = 60) -> Path:
    """Capture a single HTML scene as a high-quality video.

    1. Renders each frame as a PNG screenshot
    2. Encodes frames into WebM with ffmpeg
    """
    frames_dir = output_path.parent / f"_frames_{output_path.stem}"

    try:
        n_frames = capture_scene_frames(
            html_path, frames_dir, duration, width, height, fps
        )
        encode_frames_to_video(frames_dir, output_path, fps)
    finally:
        if frames_dir.exists():
            shutil.rmtree(frames_dir)

    return output_path


# ── Batch rendering ──────────────────────────────────────────────────────────

def render_all_scenes(html_dir: Path, scene_data_list: list,
                      output_dir: Path, width: int = 1080,
                      height: int = 1920, fps: int = 60,
                      scene_timings: list[SceneTiming | None] | None = None,
                      workers: int = 4,
                      ) -> list[Path]:
    """Render all HTML scenes to video files in parallel.

    Each scene is captured independently, so up to *workers* scenes are
    rendered concurrently (separate Playwright browser instances).

    When *scene_timings* is provided, each scene's duration is derived
    from the narration audio length instead of being estimated from
    CSS animation formulas.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    html_files = sorted(html_dir.glob("S*.html"))
    n = len(html_files)
    effective_workers = min(workers, n) if n else 1

    def _render_one(idx: int, html_file: Path, scene_data: dict) -> tuple[int, Path]:
        stem = html_file.stem
        out_path = output_dir / f"{stem}.webm"
        timing = scene_timings[idx] if scene_timings and idx < len(scene_timings) else None
        audio_dur = timing.total_duration - 0.5 if timing else None
        duration = _get_scene_duration(scene_data, audio_duration=audio_dur)
        log.info("Rendering %s (%.1fs, %d frames)...", stem, duration, int(duration * fps))
        capture_scene(html_file, out_path, duration, width, height, fps)
        return idx, out_path

    results_map: dict[int, Path] = {}

    with ThreadPoolExecutor(max_workers=effective_workers) as pool:
        futures = {
            pool.submit(_render_one, idx, html_file, scene_data): idx
            for idx, (html_file, scene_data) in enumerate(zip(html_files, scene_data_list))
        }
        for future in as_completed(futures):
            idx, out_path = future.result()   # re-raises exceptions from worker
            results_map[idx] = out_path
            log.info("Scene %d/%d done → %s", idx + 1, n, out_path.name)

    return [results_map[i] for i in range(n)]


# ── Audio helpers ─────────────────────────────────────────────────────────────

def _has_audio(path: Path) -> bool:
    cmd = ["ffprobe", "-v", "quiet", "-select_streams", "a",
           "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)]
    return bool(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())


def _add_silent_audio(video_path: Path, output_path: Path) -> Path:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-c:v", "copy", "-c:a", "libopus", "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Silent audio failed:\n{result.stderr}")
    return output_path


def _get_duration(path: Path) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 3.0


# ── Concatenation with crossfade transitions ──────────────────────────────────

def concatenate_videos(video_files: list[Path], output_path: Path,
                       crossfade: float = 0.4) -> Path:
    """Concatenate videos with crossfade transitions between scenes.

    Uses ffmpeg xfade filter for smooth scene transitions.
    Normalizes audio streams (injects silence where missing).
    """
    if not video_files:
        raise ValueError("No video files to concatenate")

    if len(video_files) == 1:
        shutil.copy2(video_files[0], output_path)
        return output_path

    # Normalize audio streams
    any_audio = any(_has_audio(vf) for vf in video_files)
    normalized = []
    tmp_files = []

    for vf in video_files:
        if any_audio and not _has_audio(vf):
            silent_path = vf.parent / f"{vf.stem}_silent.webm"
            _add_silent_audio(vf, silent_path)
            normalized.append(silent_path)
            tmp_files.append(silent_path)
        else:
            normalized.append(vf)

    # Get durations for crossfade offset calculation
    durations = [_get_duration(vf) for vf in normalized]
    n = len(normalized)

    if n == 2:
        # Simple two-input crossfade
        offset = durations[0] - crossfade
        cmd = [
            "ffmpeg", "-y",
            "-i", str(normalized[0]),
            "-i", str(normalized[1]),
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={crossfade}:offset={offset:.3f}[v];"
            f"[0:a][1:a]acrossfade=d={crossfade}[a]"
            if any_audio else
            f"[0:v][1:v]xfade=transition=fade:duration={crossfade}:offset={offset:.3f}[v]",
            "-map", "[v]",
            *(["-map", "[a]"] if any_audio else []),
            "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "18",
            "-quality", "good", "-speed", "4", "-row-mt", "1",
            *(["-c:a", "libopus"] if any_audio else []),
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Fallback to simple concat
            _simple_concat(normalized, output_path, any_audio)
    else:
        # Multi-input: chain xfade filters
        inputs = []
        for vf in normalized:
            inputs.extend(["-i", str(vf)])

        # Build video xfade chain
        v_filters = []
        offsets = []
        cumulative = 0.0
        for i in range(n - 1):
            cumulative += durations[i] - crossfade
            offsets.append(cumulative)

        # Chain: [0:v][1:v]xfade -> [v01]; [v01][2:v]xfade -> [v012]; etc.
        prev_label = "0:v"
        for i in range(1, n):
            out_label = f"v{i}"
            offset = offsets[i-1]
            v_filters.append(
                f"[{prev_label}][{i}:v]xfade=transition=fade:"
                f"duration={crossfade}:offset={offset:.3f}[{out_label}]"
            )
            prev_label = out_label

        # Audio: chain acrossfade
        a_filters = []
        if any_audio:
            a_prev = "0:a"
            for i in range(1, n):
                a_out = f"a{i}"
                a_filters.append(
                    f"[{a_prev}][{i}:a]acrossfade=d={crossfade}[{a_out}]"
                )
                a_prev = a_out

        filter_complex = ";".join(v_filters + a_filters)
        final_v = prev_label
        final_a = f"a{n-1}" if any_audio else None

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{final_v}]",
            *(["-map", f"[{final_a}]"] if final_a else []),
            "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "18",
            "-quality", "good", "-speed", "4", "-row-mt", "1",
            *(["-c:a", "libopus"] if any_audio else []),
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error("Crossfade failed, falling back to simple concat")
            _simple_concat(normalized, output_path, any_audio)

    # Cleanup
    for tf in tmp_files:
        try:
            tf.unlink()
        except OSError:
            pass

    return output_path


def _simple_concat(video_files: list[Path], output_path: Path,
                   has_audio: bool) -> Path:
    """Fallback: simple concat without transitions."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for vf in video_files:
            f.write(f"file '{vf.resolve()}'\n")
        concat_file = f.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "18",
            "-quality", "good", "-speed", "4", "-row-mt", "1",
            *(["-c:a", "libopus"] if has_audio else []),
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"concat failed:\n{result.stderr}")
    finally:
        os.unlink(concat_file)

    return output_path
