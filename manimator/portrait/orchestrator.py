#!/usr/bin/env python3
"""
Portrait video orchestrator — generates social media videos from JSON storyboards.

Usage:
    python -m manimator.portrait.orchestrator -s crispr_reel.json
    python -m manimator.portrait.orchestrator -s crispr_reel.json --narrate --voice guy
    python -m manimator.portrait.orchestrator -s crispr_reel.json --format tiktok --narrate --post-copy
"""

import argparse
import json
import sys
import time
from pathlib import Path

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

Formats: instagram_reel (default), instagram_square, youtube_short, tiktok
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

    args = parser.parse_args()
    t_start = time.time()

    # ── 1. Load storyboard ──
    print(f"[portrait] Loading: {args.storyboard}")
    with open(args.storyboard) as f:
        raw = json.load(f)

    storyboard = Storyboard(**raw)
    fmt = PORTRAIT_FORMATS[args.format]
    theme_name = storyboard.meta.color_theme
    theme = THEMES.get(theme_name, THEMES["wong"])

    print(f"[portrait] {len(storyboard.scenes)} scenes | "
          f"theme={theme_name} | format={fmt['name']} ({fmt['width']}x{fmt['height']})")

    # ── 2. Generate HTML scenes ──
    work_dir = args.storyboard.parent / f".portrait_{args.storyboard.stem}"
    html_dir = work_dir / "html"
    video_dir = work_dir / "video"
    html_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    scene_data_list = []
    for i, scene in enumerate(storyboard.scenes):
        sd = scene.model_dump()
        scene_data_list.append(sd)
        scene_id = f"S{i:02d}_{sd['id']}"

        html_content = render_scene_html(sd, theme)
        if not html_content:
            print(f"  [SKIP] Unknown scene type: {sd.get('type')}")
            continue

        html_file = html_dir / f"{scene_id}.html"
        html_file.write_text(html_content)

    print(f"[portrait] Generated {len(list(html_dir.glob('*.html')))} HTML scenes")

    # ── 3. Capture videos ──
    t_render = time.time()
    video_files = render_all_scenes(
        html_dir, scene_data_list, video_dir,
        width=fmt["width"], height=fmt["height"], fps=args.fps,
    )
    print(f"[portrait] Captured in {time.time() - t_render:.1f}s")

    # ── 4. Narration ──
    if args.narrate:
        from manimator.narration import (
            generate_narration_script, synthesize_audio,
            merge_audio_video, VOICES,
        )

        voice = VOICES.get(args.voice, args.voice)
        audio_dir = work_dir / "audio"
        audio_dir.mkdir(exist_ok=True)

        narrated_files = []
        for vf, scene in zip(video_files, storyboard.scenes):
            sd = scene.model_dump()
            script = generate_narration_script(sd)

            if not script.strip():
                narrated_files.append(vf)
                continue

            scene_id = vf.stem
            audio_path = audio_dir / f"{scene_id}.mp3"
            print(f'  [{scene_id}] "{script[:50]}..."')

            try:
                synthesize_audio(script, audio_path, voice=voice, rate=args.rate)
                narrated = vf.parent / f"{scene_id}_narrated.webm"
                merge_audio_video(vf, audio_path, narrated)
                narrated_files.append(narrated)
            except Exception as e:
                print(f"  [{scene_id}] TTS failed, using silent: {e}")
                narrated_files.append(vf)

        video_files = narrated_files
        print("[portrait] Narration complete")

    # ── 5. Concatenate ──
    output = args.output
    if output is None:
        output = args.storyboard.parent / f"{args.storyboard.stem}_{args.format}.webm"

    concatenate_videos(
        [Path(v) for v in video_files],
        output,
    )
    file_size = output.stat().st_size / (1024 * 1024)

    # ── 6. Post copy ──
    if args.post_copy:
        from manimator.social import generate_post_copy
        post = generate_post_copy(raw, args.format)
        copy_file = output.with_suffix(".txt")
        with open(copy_file, "w") as f:
            f.write(f"=== {fmt['name']} Post Copy ===\n\n")
            f.write(post["caption"])
            f.write(f"\n\n=== Hook Text ===\n{post['hook_text']}\n")
        print(f"[portrait] Post copy saved: {copy_file}")

    total = time.time() - t_start
    print(f"[portrait] Done! {output} ({file_size:.1f} MB) in {total:.0f}s")


if __name__ == "__main__":
    main()
