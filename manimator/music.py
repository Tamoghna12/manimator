"""Background music mixing for manimator videos.

Supports three presets (ambient, corporate, cinematic) with automatic
looping and volume ducking under narration via ffmpeg sidechaincompress.
Preset tones are generated locally via ffmpeg on first use and cached
in ``~/.cache/manimator/music/``.  Users can also pass a path to any
MP3 file instead of a preset name.
"""

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "manimator" / "music"

# Preset definitions — generated locally via ffmpeg (no network needed)
MUSIC_PRESETS = {
    "ambient": {
        "filename": "ambient_loop.mp3",
        "description": "Soft ambient pad, ideal for science explainers",
        "ffmpeg_filter": (
            "sine=frequency=174:duration=30[s1];"
            "sine=frequency=220:duration=30[s2];"
            "sine=frequency=261:duration=30[s3];"
            "[s1][s2][s3]amix=inputs=3:duration=first[mix];"
            "[mix]lowpass=f=300,volume=0.08,afade=t=in:d=2,afade=t=out:st=28:d=2"
        ),
    },
    "corporate": {
        "filename": "corporate_loop.mp3",
        "description": "Upbeat corporate background, suits product demos",
        "ffmpeg_filter": (
            "sine=frequency=330:duration=30[s1];"
            "sine=frequency=440:duration=30[s2];"
            "[s1][s2]amix=inputs=2:duration=first[mix];"
            "[mix]lowpass=f=500,tremolo=f=4:d=0.3,volume=0.08,"
            "afade=t=in:d=1,afade=t=out:st=28:d=2"
        ),
    },
    "cinematic": {
        "filename": "cinematic_loop.mp3",
        "description": "Dramatic cinematic underscore for high-impact content",
        "ffmpeg_filter": (
            "sine=frequency=110:duration=30[s1];"
            "sine=frequency=165:duration=30[s2];"
            "sine=frequency=82:duration=30[s3];"
            "[s1][s2][s3]amix=inputs=3:duration=first[mix];"
            "[mix]lowpass=f=250,volume=0.10,afade=t=in:d=3,afade=t=out:st=27:d=3"
        ),
    },
}


def _get_duration(path: Path) -> float:
    """Get media duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def ensure_music_asset(preset: str) -> Path:
    """Generate a music preset if not cached, return local path.

    If *preset* is not a known preset name it is treated as a local
    file path and returned directly.
    """
    if preset not in MUSIC_PRESETS:
        p = Path(preset)
        if p.is_file():
            return p
        raise FileNotFoundError(
            f"Unknown music preset '{preset}' and path does not exist"
        )

    info = MUSIC_PRESETS[preset]
    cached = CACHE_DIR / info["filename"]
    if cached.exists() and cached.stat().st_size > 1024:
        return cached

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Generating music preset '%s' → %s", preset, cached)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", info["ffmpeg_filter"],
        "-c:a", "libmp3lame", "-q:a", "4",
        str(cached),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to generate music preset '{preset}': {result.stderr}"
        )

    return cached


def _loop_music_to_length(music_path: Path, target_seconds: float,
                          output_path: Path) -> Path:
    """Loop *music_path* so it fills at least *target_seconds*."""
    music_dur = _get_duration(music_path)
    if music_dur <= 0:
        raise RuntimeError(f"Cannot determine duration of {music_path}")

    if music_dur >= target_seconds:
        # Trim to target length
        cmd = [
            "ffmpeg", "-y",
            "-i", str(music_path),
            "-t", f"{target_seconds:.3f}",
            "-c:a", "copy",
            str(output_path),
        ]
    else:
        # Loop and trim
        loops = int(target_seconds / music_dur) + 1
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", str(loops),
            "-i", str(music_path),
            "-t", f"{target_seconds:.3f}",
            "-c:a", "libmp3lame", "-q:a", "4",
            str(output_path),
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Music loop failed:\n{result.stderr}")
    return output_path


def add_background_music(video_path: Path, music: str,
                         output_path: Path, duck_level: float = 0.2) -> Path:
    """Mix background music into *video_path*, ducking under narration.

    Parameters
    ----------
    video_path : Path
        Input video (must have an audio track for ducking to work).
    music : str
        Preset name ('ambient', 'corporate', 'cinematic') or path to MP3.
    output_path : Path
        Where to write the mixed result.
    duck_level : float
        Music volume multiplier when narration is active (0.0–1.0).
        Default 0.2 means music drops to 20 % under speech.

    Returns the *output_path*.
    """
    music_path = ensure_music_asset(music)
    video_dur = _get_duration(video_path)

    # Prepare looped music file matching video length
    looped = output_path.parent / f"_music_looped_{output_path.stem}.mp3"
    try:
        _loop_music_to_length(music_path, video_dur, looped)

        # Try sidechain compression first (proper ducking)
        if _try_sidechain_mix(video_path, looped, output_path, duck_level):
            return output_path

        # Fallback: simple amix with reduced music volume
        log.warning("Sidechain compress unavailable, falling back to amix")
        _simple_amix(video_path, looped, output_path, duck_level)
        return output_path
    finally:
        if looped.exists():
            try:
                looped.unlink()
            except OSError:
                pass


def _try_sidechain_mix(video_path: Path, music_path: Path,
                       output_path: Path, duck_level: float) -> bool:
    """Attempt sidechain-compressed mix. Returns True on success."""
    # The sidechaincompress filter ducks music when narration is present.
    # [1:a] = music, [0:a] = narration (sidechain source).
    filter_complex = (
        f"[1:a]volume=0.35[music];"
        f"[0:a]asplit=2[narr][sc];"
        f"[music][sc]sidechaincompress="
        f"threshold=0.02:ratio=8:attack=80:release=500:"
        f"level_sc=1:level_in={duck_level:.2f}[ducked];"
        f"[narr][ducked]amix=inputs=2:duration=first:dropout_transition=2[out]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(music_path),
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[out]",
        "-c:v", "copy", "-c:a", "libopus",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def _simple_amix(video_path: Path, music_path: Path,
                 output_path: Path, duck_level: float) -> None:
    """Fallback: mix music at reduced volume without ducking."""
    filter_complex = (
        f"[1:a]volume={duck_level:.2f}[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[out]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(music_path),
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[out]",
        "-c:v", "copy", "-c:a", "libopus",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Music amix failed:\n{result.stderr}")
