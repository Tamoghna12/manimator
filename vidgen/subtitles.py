"""Generate and burn subtitles into video."""

import subprocess
import json
import asyncio
from pathlib import Path

import edge_tts


async def _generate_srt(text: str, output_srt: Path, output_audio: Path,
                        voice: str = "en-US-AriaNeural", rate: str = "-5%"):
    """Generate SRT subtitle file from text using edge-tts word boundaries."""
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    subs = []
    current_sub = {"start": 0, "end": 0, "words": []}
    word_count = 0

    async for chunk in communicate.stream():
        if chunk["type"] == "WordBoundary":
            offset_ms = chunk["offset"] / 10000  # Convert to milliseconds
            duration_ms = chunk["duration"] / 10000
            word = chunk["text"]

            current_sub["words"].append(word)
            current_sub["end"] = offset_ms + duration_ms
            word_count += 1

            # Split subtitles every 6-8 words or at punctuation
            if (word_count >= 7 or
                    (word_count >= 4 and word.rstrip().endswith((".", ",", "!", "?", ";", ":")))):
                subs.append({
                    "start": current_sub["start"],
                    "end": current_sub["end"],
                    "text": " ".join(current_sub["words"]),
                })
                current_sub = {"start": current_sub["end"], "end": 0, "words": []}
                word_count = 0

        elif chunk["type"] == "audio":
            pass  # Audio data handled by save

    # Flush remaining
    if current_sub["words"]:
        subs.append({
            "start": current_sub["start"],
            "end": current_sub["end"],
            "text": " ".join(current_sub["words"]),
        })

    # Write SRT file
    with open(output_srt, "w") as f:
        for i, sub in enumerate(subs, 1):
            start_ts = _ms_to_srt_time(sub["start"])
            end_ts = _ms_to_srt_time(sub["end"])
            f.write(f"{i}\n{start_ts} --> {end_ts}\n{sub['text']}\n\n")

    # Also save the audio
    await edge_tts.Communicate(text, voice, rate=rate).save(str(output_audio))

    return subs


def _ms_to_srt_time(ms: float) -> str:
    """Convert milliseconds to SRT timestamp format."""
    total_ms = int(ms)
    hours = total_ms // 3600000
    minutes = (total_ms % 3600000) // 60000
    seconds = (total_ms % 60000) // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def generate_subtitles(text: str, output_srt: Path, output_audio: Path,
                       voice: str = "en-US-AriaNeural", rate: str = "-5%"):
    """Blocking wrapper for subtitle generation."""
    return asyncio.run(_generate_srt(text, output_srt, output_audio, voice, rate))


def burn_subtitles(video_path: Path, srt_path: Path, audio_path: Path,
                   output_path: Path, style: str = "social"):
    """Burn SRT subtitles into video and merge audio.

    style: "social" = large bold white text with black outline (mobile-friendly)
           "academic" = smaller, bottom-positioned subtitles
    """
    if style == "social":
        # Large, centered, bold subtitles optimized for mobile
        sub_filter = (
            f"subtitles={srt_path}:force_style='"
            "FontName=Arial,FontSize=28,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=3,Bold=1,"
            "Alignment=2,MarginV=80'"
        )
    else:
        sub_filter = (
            f"subtitles={srt_path}:force_style='"
            "FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H80000000,Outline=2,Bold=0,"
            "Alignment=2,MarginV=40'"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex",
        f"[0:v]{sub_filter}[v]",
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libvpx-vp9", "-c:a", "libopus",
        "-shortest",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Subtitle burn failed:\n{result.stderr}")
