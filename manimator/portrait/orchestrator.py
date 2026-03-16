#!/usr/bin/env python3
"""
Portrait video orchestrator — generates social media videos from JSON storyboards.

Usage:
    python -m manimator.portrait.orchestrator -s crispr_reel.json
    python -m manimator.portrait.orchestrator -s crispr_reel.json --narrate --voice guy
    python -m manimator.portrait.orchestrator -s crispr_reel.json --format tiktok --narrate --post-copy
    python -m manimator.portrait.orchestrator -s crispr_reel.json --narrate --music ambient
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

from manimator.schema import Storyboard
from manimator.config import THEMES
from manimator.portrait.html_scenes import render_scene_html
from manimator.portrait.renderer import (
    render_all_scenes, concatenate_videos, _get_scene_duration,
)


# Portrait format profiles
PORTRAIT_FORMATS = {
    "instagram_reel": {"width": 1080, "height": 1920, "name": "Instagram Reel",
                       "max_duration": 90, "pacing": "fast"},
    "instagram_square": {"width": 1080, "height": 1080, "name": "Instagram Square",
                         "max_duration": 60, "pacing": "fast"},
    "youtube_short": {"width": 1080, "height": 1920, "name": "YouTube Short",
                      "max_duration": 60, "pacing": "fast"},
    "tiktok": {"width": 1080, "height": 1920, "name": "TikTok",
               "max_duration": 60, "pacing": "fast"},
}


def main():
    parser = argparse.ArgumentParser(
        description="Generate portrait social media videos from JSON storyboards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -s topic.json                              # Instagram Reel
  %(prog)s -s topic.json --format tiktok --narrate     # TikTok + voiceover
  %(prog)s -s topic.json --narrate --post-copy          # Full pipeline
  %(prog)s -s topic.json --format instagram_square     # Square format
  %(prog)s -s topic.json --narrate --music ambient     # With background music

Formats: instagram_reel (default), instagram_square, youtube_short, tiktok
Music presets: ambient, corporate, cinematic (or path to MP3 file)
        """,
    )
    parser.add_argument("--storyboard", "-s", required=True, type=Path)
    parser.add_argument("--output", "-o", type=Path, default=None)
    parser.add_argument(
        "--format", "-f", default="instagram_reel",
        choices=list(PORTRAIT_FORMATS.keys()),
    )
    parser.add_argument("--narrate", action="store_true", help="Add AI voiceover")
    parser.add_argument("--post-copy", action="store_true", help="Generate post copy")
    parser.add_argument(
        "--voice", default="aria",
        choices=["aria", "guy", "jenny", "davis", "andrew", "emma"],
    )
    parser.add_argument("--rate", default="-5%", help="Speech rate")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Parallel scene renderers (Playwright instances). Default: 4",
    )
    parser.add_argument(
        "--music", default=None,
        help="Background music preset (ambient/corporate/cinematic) or path to MP3",
    )

    args = parser.parse_args()
    t_start = time.time()

    # ── 1. Load storyboard ──
    log.info("Loading: %s", args.storyboard)
    with open(args.storyboard) as f:
        raw = json.load(f)

    storyboard = Storyboard(**raw)
    fmt = PORTRAIT_FORMATS[args.format]
    theme_name = storyboard.meta.color_theme
    theme = THEMES.get(theme_name, THEMES["wong"])

    # Music can come from CLI or storyboard meta
    music = args.music or storyboard.meta.background_music

    # Extract branding dict for HTML renderers
    branding = (storyboard.meta.branding.model_dump()
                if storyboard.meta.branding else None)

    log.info("%d scenes | theme=%s | format=%s (%dx%d)",
             len(storyboard.scenes), theme_name,
             fmt['name'], fmt['width'], fmt['height'])

    # ── 2. Work directories ──
    work_dir = args.storyboard.parent / f".portrait_{args.storyboard.stem}"
    html_dir = work_dir / "html"
    video_dir = work_dir / "video"
    html_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    scene_data_list = []
    for scene in storyboard.scenes:
        scene_data_list.append(scene.model_dump())

    # ── 3. Narration-first pipeline (when --narrate) ──
    scene_timings = None
    scene_audios = None

    if args.narrate:
        from manimator.narration import (
            generate_narration_script, generate_narration_chunks,
            synthesize_chunks, concatenate_audio_chunks,
            compute_element_delays, synthesize_audio,
            merge_audio_video, get_audio_duration, VOICES,
        )
        from manimator.timing import SceneTiming

        voice = VOICES.get(args.voice, args.voice)
        audio_dir = work_dir / "audio"
        audio_dir.mkdir(exist_ok=True)

        scene_timings = []
        scene_audios = []

        for i, sd in enumerate(scene_data_list):
            scene_id = f"S{i:02d}_{sd['id']}"
            script = generate_narration_script(sd)

            if not script.strip():
                scene_timings.append(None)
                scene_audios.append(None)
                continue

            log.info('[%s] Generating narration chunks...', scene_id)

            try:
                chunks = generate_narration_chunks(sd)
                chunk_results = synthesize_chunks(
                    chunks, audio_dir, scene_id,
                    voice=voice, rate=args.rate,
                )
                chunk_paths = [p for p, _ in chunk_results]
                chunk_durations = [d for _, d in chunk_results]

                # Compute element delays from chunk durations
                delays = compute_element_delays(chunk_durations)

                # Concatenate chunks into one audio file per scene
                combined_audio = audio_dir / f"{scene_id}.mp3"
                concatenate_audio_chunks(chunk_paths, combined_audio)

                total_dur = sum(chunk_durations)
                timing = SceneTiming(
                    total_duration=total_dur + 0.5,
                    element_delays=delays,
                )
                scene_timings.append(timing)
                scene_audios.append(combined_audio)

                log.info('[%s] %d chunks, %.1fs total', scene_id, len(chunks), total_dur)
            except Exception as e:
                log.error("[%s] Chunk narration failed, falling back to simple: %s", scene_id, e)
                # Fallback: single-chunk synthesis
                try:
                    audio_path = audio_dir / f"{scene_id}.mp3"
                    synthesize_audio(script, audio_path, voice=voice, rate=args.rate)
                    dur = get_audio_duration(audio_path)
                    timing = SceneTiming(total_duration=dur + 0.5)
                    scene_timings.append(timing)
                    scene_audios.append(audio_path)
                except Exception as e2:
                    log.error("[%s] TTS failed entirely: %s", scene_id, e2)
                    scene_timings.append(None)
                    scene_audios.append(None)

        log.info("Narration synthesis complete")

    # ── 4. Generate HTML scenes (with timing when available) ──
    for i, sd in enumerate(scene_data_list):
        scene_id = f"S{i:02d}_{sd['id']}"
        timing = scene_timings[i] if scene_timings and i < len(scene_timings) else None

        html_content = render_scene_html(sd, theme, timing=timing, branding=branding)
        if not html_content:
            log.info("[SKIP] Unknown scene type: %s", sd.get('type'))
            continue

        html_file = html_dir / f"{scene_id}.html"
        html_file.write_text(html_content)

    log.info("Generated %d HTML scenes", len(list(html_dir.glob('*.html'))))

    # ── 5. Capture videos (with timing-derived durations) ──
    t_render = time.time()
    video_files = render_all_scenes(
        html_dir, scene_data_list, video_dir,
        width=fmt["width"], height=fmt["height"], fps=args.fps,
        scene_timings=scene_timings, workers=args.workers,
    )
    log.info("Captured in %.1fs", time.time() - t_render)

    # ── 6. Merge audio + video (narration mode) ──
    if args.narrate and scene_audios:
        from manimator.narration import merge_audio_video

        narrated_files = []
        for vf, audio in zip(video_files, scene_audios):
            if audio is None or not audio.exists():
                narrated_files.append(vf)
                continue

            try:
                narrated = vf.parent / f"{vf.stem}_narrated.mp4"
                merge_audio_video(vf, audio, narrated)
                narrated_files.append(narrated)
            except Exception as e:
                log.error("[%s] Audio merge failed, using silent: %s", vf.stem, e)
                narrated_files.append(vf)

        video_files = narrated_files
        log.info("Audio merge complete")

    # ── 7. Concatenate ──
    output = args.output
    if output is None:
        output = args.storyboard.parent / f"{args.storyboard.stem}_{args.format}.mp4"

    scene_types = [sd.get("type", "") for sd in scene_data_list]
    concatenate_videos(
        [Path(v) for v in video_files],
        output,
        scene_types=scene_types,
    )
    file_size = output.stat().st_size / (1024 * 1024)

    # ── 8. Background music ──
    if music:
        from manimator.music import add_background_music

        music_output = output.parent / f"{output.stem}_music{output.suffix}"
        try:
            add_background_music(output, music, music_output)
            # Replace original with music version
            music_output.replace(output)
            log.info("Background music applied: %s", music)
        except Exception as e:
            log.error("Background music failed: %s", e)
            # Clean up partial output
            if music_output.exists():
                music_output.unlink()

    # ── 9. Post copy ──
    if args.post_copy:
        from manimator.social import generate_post_copy
        post = generate_post_copy(raw, args.format)
        copy_file = output.with_suffix(".txt")
        with open(copy_file, "w") as f:
            f.write(f"=== {fmt['name']} Post Copy ===\n\n")
            f.write(post["caption"])
            f.write(f"\n\n=== Hook Text ===\n{post['hook_text']}\n")
        log.info("Post copy saved: %s", copy_file)

    total = time.time() - t_start
    log.info("Done! %s (%.1f MB) in %.0fs", output, file_size, total)


if __name__ == "__main__":
    main()
