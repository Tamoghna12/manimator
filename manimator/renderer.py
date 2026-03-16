"""Render Manim scenes and concatenate into final video."""

import subprocess
import os
import tempfile
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor


def render_scene(args: tuple) -> str:
    """Render a single scene. Returns the output file path."""
    gen_file, class_name, quality, output_dir = args
    gen_file = Path(gen_file).resolve()
    quality_flag = {"low": "-ql", "medium": "-qm", "high": "-qh"}[quality]

    cmd = [
        "manim", quality_flag, "--disable_caching",
        str(gen_file), class_name,
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(gen_file.parent),
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Manim render failed for {class_name}:\n{result.stderr}"
        )

    # Find the output file
    # Manim names dirs by pixel_height + fps, e.g. "1080p60", "1920p15"
    stem = gen_file.stem
    videos_dir = gen_file.parent / "media" / "videos" / stem

    # Try known patterns first, then search
    fps_map = {"low": 15, "medium": 30, "high": 60}
    fps = fps_map[quality]

    output_file = None
    if videos_dir.exists():
        # Search all resolution dirs for the class name
        for res_dir in sorted(videos_dir.iterdir(), reverse=True):
            if not res_dir.is_dir():
                continue
            candidate = res_dir / f"{class_name}.mp4"
            if candidate.exists():
                output_file = candidate
                break
            # Also check other extensions
            for f in res_dir.glob(f"{class_name}.*"):
                if f.suffix in (".webm", ".mp4", ".mov"):
                    output_file = f
                    break
            if output_file:
                break

    if output_file is None:
        raise FileNotFoundError(
            f"No output found for {class_name} in {videos_dir}. "
            f"Dir contents: {list(videos_dir.iterdir()) if videos_dir.exists() else 'N/A'}"
        )

    return str(output_file.resolve())


def generate_thumbnail(video_path: Path, output_path: Path,
                       timestamp: str = "00:00:02"):
    """Extract a thumbnail frame from a video."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-ss", timestamp,
        "-vframes", "1",
        "-q:v", "2",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Thumbnail generation failed:\n{result.stderr}")


def render_all(gen_file: Path, class_names: list[str],
               quality: str = "high", workers: int = 4) -> list[str]:
    """Render all scenes, optionally in parallel."""
    gen_file = gen_file.resolve()
    output_dir = gen_file.parent
    args_list = [(gen_file, cn, quality, output_dir) for cn in class_names]

    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(render_scene, args_list))
    else:
        results = [render_scene(a) for a in args_list]

    return results


def _has_audio_stream(video_path: str) -> bool:
    """Check if a video file contains an audio stream."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return bool(result.stdout.strip())


def _add_silent_audio(video_path: str, output_path: str) -> str:
    """Add a silent audio track to a video-only file."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-c:v", "copy", "-c:a", "libopus",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to add silent audio:\n{result.stderr}")
    return output_path


def concatenate(video_files: list[str], output_path: Path,
                ffmpeg_bin: str = "ffmpeg"):
    """Concatenate video files using ffmpeg concat demuxer.

    Normalizes all segments to include an audio stream so that
    mixed silent/narrated segments concatenate correctly.
    """
    # Check if any file has audio — if so, all must have audio
    any_audio = any(_has_audio_stream(vf) for vf in video_files)

    normalized = []
    tmp_files = []
    for vf in video_files:
        if any_audio and not _has_audio_stream(vf):
            # Add silent audio track so concat works
            silent_path = vf.rsplit(".", 1)[0] + "_silent.mp4"
            _add_silent_audio(vf, silent_path)
            normalized.append(silent_path)
            tmp_files.append(silent_path)
        else:
            normalized.append(vf)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for vf in normalized:
            f.write(f"file '{vf}'\n")
        concat_file = f.name

    try:
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed:\n{result.stderr}")
    finally:
        os.unlink(concat_file)
        for tf in tmp_files:
            try:
                os.unlink(tf)
            except OSError:
                pass

    return str(output_path)
