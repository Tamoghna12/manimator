"""Render Manim scenes and concatenate into final video."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
QUALITY_FLAGS: dict[str, str] = {
    "low":    "-ql",
    "medium": "-qm",
    "high":   "-qh",
    "4k":     "-qk",
}
QUALITY_FPS: dict[str, int] = {
    "low": 15, "medium": 30, "high": 60, "4k": 60,
}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv"}

# EBU R128 target loudness (-16 LUFS matches YouTube/Shorts spec) [web:113][web:117]
LUFS_TARGET   = -16.0
LRA_TARGET    = 11.0
TRUE_PEAK     = -1.5
RENDER_TIMEOUT = 600      # seconds per scene before kill
MAX_RETRIES    = 2


# ── Data types ────────────────────────────────────────────────────────────

@dataclass
class RenderResult:
    class_name: str
    output_path: Path
    duration_s: float
    retries: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class RenderError:
    class_name: str
    stderr: str
    attempts: int


# ── Scene output discovery ─────────────────────────────────────────────────

def _find_output(gen_file: Path, class_name: str) -> Path | None:
    """
    Search Manim's media tree for a rendered scene file.
    Handles the `{stem}/{resolution}p{fps}/{ClassName}.{ext}` layout
    as well as partial/custom paths Manim may emit.
    """
    videos_dir = gen_file.parent / "media" / "videos" / gen_file.stem
    if not videos_dir.exists():
        return None

    # Walk all resolution sub-directories, preferring highest resolution
    for res_dir in sorted(videos_dir.iterdir(), reverse=True):
        if not res_dir.is_dir():
            continue
        for ext in (".mp4", ".webm", ".mov", ".mkv"):
            candidate = res_dir / f"{class_name}{ext}"
            if candidate.exists():
                return candidate.resolve()
    return None


# ── ffprobe helpers ────────────────────────────────────────────────────────

def _probe(video_path: str | Path, select: str, entries: str) -> str:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", select,
        "-show_entries", entries,
        "-of", "csv=p=0",
        str(video_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip()


def _has_audio(video_path: str | Path) -> bool:
    return bool(_probe(video_path, "a", "stream=codec_type"))


def _video_duration(video_path: str | Path) -> float:
    """Return duration in seconds via ffprobe."""
    out = _probe(video_path, "v:0", "stream=duration")
    try:
        return float(out.splitlines()[0])
    except (ValueError, IndexError):
        return 0.0


# ── Audio helpers ──────────────────────────────────────────────────────────

def _add_silent_audio(video_path: Path, output_path: Path) -> Path:
    """Mux in a silent stereo audio track (48 kHz Opus)."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-i", str(video_path),
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-c:v", "copy", "-c:a", "libopus", "-b:a", "64k",
        "-shortest",
        str(output_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Silent-audio mux failed:\n{r.stderr}")
    return output_path


def _measure_loudness(video_path: Path) -> dict[str, float]:
    """
    EBU R128 first-pass measurement via loudnorm.
    Returns dict with keys: input_i, input_lra, input_tp, input_thresh.
    [web:113][web:117]
    """
    cmd = [
        "ffmpeg", "-hide_banner",
        "-i", str(video_path),
        "-af", (
            f"loudnorm=I={LUFS_TARGET}:LRA={LRA_TARGET}:TP={TRUE_PEAK}"
            ":print_format=json"
        ),
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    # loudnorm JSON is emitted on stderr
    for line in reversed(r.stderr.splitlines()):
        if line.strip().startswith("{"):
            try:
                blob = "\n".join(
                    r.stderr[r.stderr.rfind("{"):]
                    .split("\n")
                )
                return json.loads(blob)
            except json.JSONDecodeError:
                break
    return {}


def _normalise_audio(
    video_path: Path,
    output_path: Path,
    two_pass: bool = True,
) -> Path:
    """
    EBU R128 loudness normalisation.
    Two-pass mode uses measured stats from pass 1 for higher accuracy. [web:113]
    Falls back to single-pass if measurement fails.
    """
    if two_pass:
        stats = _measure_loudness(video_path)
    else:
        stats = {}

    if stats and all(k in stats for k in ("input_i", "input_lra", "input_tp", "input_thresh")):
        # Pass 2: apply measured values
        af = (
            f"loudnorm=I={LUFS_TARGET}:LRA={LRA_TARGET}:TP={TRUE_PEAK}"
            f":measured_I={stats['input_i']}"
            f":measured_LRA={stats['input_lra']}"
            f":measured_tp={stats['input_tp']}"
            f":measured_thresh={stats['input_thresh']}"
            ":linear=true:print_format=summary"
        )
    else:
        # Single-pass fallback
        af = f"loudnorm=I={LUFS_TARGET}:LRA={LRA_TARGET}:TP={TRUE_PEAK}"

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-i", str(video_path),
        "-af", af,
        "-c:v", "copy",
        "-c:a", "libopus", "-b:a", "128k",
        str(output_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Loudness normalisation failed:\n{r.stderr}")
    return output_path


# ── Scene render (runs in worker process) ─────────────────────────────────

def _render_scene_worker(
    gen_file: str,
    class_name: str,
    quality: str,
) -> tuple[str, float]:
    """
    Render one Manim scene. Returns (output_path, duration_s).
    Raises RuntimeError / FileNotFoundError on failure.
    Runs inside a ProcessPoolExecutor worker.
    """
    gen_path = Path(gen_file).resolve()
    flag = QUALITY_FLAGS.get(quality, "-qh")

    cmd = [
        "manim", flag,
        "--disable_caching",
        "--progress_bar", "none",
        str(gen_path), class_name,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            cwd=str(gen_path.parent),
            timeout=RENDER_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Scene '{class_name}' timed out after {RENDER_TIMEOUT}s"
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"Manim render failed for '{class_name}':\n{result.stderr[-3000:]}"
        )

    output_file = _find_output(gen_path, class_name)
    if output_file is None:
        raise FileNotFoundError(
            f"No output found for '{class_name}' after successful render.\n"
            f"Searched: {gen_path.parent / 'media' / 'videos' / gen_path.stem}"
        )

    duration = _video_duration(output_file)
    return str(output_file), duration


# ── Public render API ──────────────────────────────────────────────────────

def render_scene(
    gen_file: Path,
    class_name: str,
    quality: str = "high",
    max_retries: int = MAX_RETRIES,
    on_progress: Callable[[str, str], None] | None = None,
) -> RenderResult:
    """
    Render a single scene with retry + exponential backoff. [web:118][web:122]
    `on_progress(class_name, status)` is called on each attempt.
    """
    gen_file = Path(gen_file).resolve()
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait = 2 ** attempt          # 2s, 4s, 8s …
            log.warning("Retry %d/%d for '%s' (waiting %ds)",
                        attempt, max_retries, class_name, wait)
            time.sleep(wait)

        status = f"rendering (attempt {attempt + 1})"
        if on_progress:
            on_progress(class_name, status)

        try:
            path_str, dur = _render_scene_worker(
                str(gen_file), class_name, quality,
            )
            if on_progress:
                on_progress(class_name, f"done ({dur:.1f}s)")
            return RenderResult(
                class_name=class_name,
                output_path=Path(path_str),
                duration_s=dur,
                retries=attempt,
            )
        except Exception as exc:
            log.error("Attempt %d failed for '%s': %s", attempt + 1, class_name, exc)
            last_error = exc

    raise RuntimeError(
        f"Scene '{class_name}' failed after {max_retries + 1} attempts"
    ) from last_error


def render_all(
    gen_file: Path,
    class_names: list[str],
    quality: str = "high",
    workers: int = 4,
    max_retries: int = MAX_RETRIES,
    on_progress: Callable[[str, str], None] | None = None,
) -> list[RenderResult]:
    """
    Render all scenes, collecting results in submission order.
    Uses a process pool for parallelism; failed futures are retried
    before the pool shuts down. [web:118]
    """
    gen_file = Path(gen_file).resolve()
    results: dict[str, RenderResult] = {}
    errors:  dict[str, Exception]    = {}

    if workers <= 1:
        for cn in class_names:
            try:
                results[cn] = render_scene(
                    gen_file, cn, quality, max_retries, on_progress,
                )
            except Exception as exc:
                errors[cn] = exc
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(_render_scene_worker,
                            str(gen_file), cn, quality): cn
                for cn in class_names
            }
            for future in as_completed(future_map):
                cn = future_map[future]
                try:
                    path_str, dur = future.result()
                    results[cn] = RenderResult(
                        class_name=cn,
                        output_path=Path(path_str),
                        duration_s=dur,
                    )
                    if on_progress:
                        on_progress(cn, f"done ({dur:.1f}s)")
                except Exception as exc:
                    log.warning("Pool render failed for '%s': %s — retrying", cn, exc)
                    # Retry sequentially outside the pool [web:118]
                    try:
                        results[cn] = render_scene(
                            gen_file, cn, quality, max_retries, on_progress,
                        )
                    except Exception as retry_exc:
                        errors[cn] = retry_exc

    if errors:
        msgs = "\n".join(f"  {cn}: {e}" for cn, e in errors.items())
        raise RuntimeError(f"The following scenes failed:\n{msgs}")

    return [results[cn] for cn in class_names]


# ── Thumbnail extraction ───────────────────────────────────────────────────

def generate_thumbnail(
    video_path: Path,
    output_path: Path,
    timestamp: str = "00:00:02",
    width: int = 1280,
) -> Path:
    """
    Extract a JPEG thumbnail scaled to `width` pixels wide.
    Uses the 'thumbnail' filter for smarter frame selection over 100 frames.
    """
    vf = f"thumbnail=100,scale={width}:-2"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-i", str(video_path),
        "-ss", timestamp,
        "-vf", vf,
        "-vframes", "1",
        "-q:v", "2",
        str(output_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Thumbnail generation failed:\n{r.stderr}")
    return output_path.resolve()


# ── Concatenation pipeline ────────────────────────────────────────────────

def concatenate(
    video_files: list[str | Path],
    output_path: Path,
    normalise_audio: bool = True,
    two_pass_loudnorm: bool = True,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    """
    Concatenate video segments using the ffmpeg concat demuxer.

    Pipeline:
      1. Ensure every segment has an audio track (add silent track if not).
      2. Optionally apply EBU R128 two-pass loudness normalisation per segment
         so narrated and silent segments blend seamlessly. [web:113][web:117]
      3. Write a concat list file and call ffmpeg -f concat.
      4. Clean up all temporary files.

    Returns the resolved output path.
    """
    video_files = [Path(vf).resolve() for vf in video_files]
    output_path = Path(output_path).resolve()

    any_audio = any(_has_audio(vf) for vf in video_files)
    tmp_dir   = tempfile.mkdtemp(prefix="manimator_concat_")
    tmp_paths: list[Path] = []

    try:
        normalised: list[Path] = []

        for i, vf in enumerate(video_files):
            current = vf

            # Step 1: add silent audio if needed
            if any_audio and not _has_audio(current):
                silent_out = Path(tmp_dir) / f"silent_{i}{current.suffix}"
                current = _add_silent_audio(current, silent_out)
                tmp_paths.append(current)
                log.debug("Added silent audio to %s", vf.name)

            # Step 2: EBU R128 normalisation per segment [web:113]
            if normalise_audio and _has_audio(current):
                norm_out = Path(tmp_dir) / f"norm_{i}{current.suffix}"
                try:
                    current = _normalise_audio(current, norm_out, two_pass_loudnorm)
                    tmp_paths.append(current)
                    log.debug("Normalised audio for segment %d", i)
                except RuntimeError as exc:
                    log.warning("Loudnorm failed for segment %d, skipping: %s", i, exc)

            normalised.append(current)

        # Step 3: write concat list
        concat_list = Path(tmp_dir) / "concat.txt"
        with concat_list.open("w") as f:
            for vf in normalised:
                f.write(f"file '{vf}'\n")

        # Step 4: concatenate
        cmd = [
            ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "warning",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed:\n{r.stderr}")

        log.info("Concatenated %d segments → %s", len(normalised), output_path)
        return output_path

    finally:
        # Step 5: clean up every temp file
        for tp in tmp_paths:
            try:
                tp.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            concat_list.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

