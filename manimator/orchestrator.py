#!/usr/bin/env python3
"""
manimator — Automated scientific video generation from JSON storyboards.

Usage:
    # Standard presentation video:
    python -m manimator.orchestrator -s my_video.json

    # Instagram Reel with narration + subtitles:
    python -m manimator.orchestrator -s my_video.json --format instagram_reel --narrate --subtitles

    # LinkedIn post with post copy:
    python -m manimator.orchestrator -s my_video.json --format linkedin --narrate --post-copy

    # Quick preview:
    python -m manimator.orchestrator -s my_video.json -q low

    # Parallel rendering:
    python -m manimator.orchestrator -s my_video.json -w 4
"""

import argparse
import json
import sys
import time
from pathlib import Path

from manimator.schema import Storyboard
from manimator.codegen import generate
from manimator.renderer import render_all, concatenate
from manimator.social import FORMATS, generate_post_copy


def main():
    parser = argparse.ArgumentParser(
        description="Generate scientific videos from JSON storyboards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -s topic.json                                    # 1080p presentation
  %(prog)s -s topic.json --format instagram_reel --narrate  # IG Reel + voiceover
  %(prog)s -s topic.json --format linkedin --subtitles      # LinkedIn + captions
  %(prog)s -s topic.json -q low                             # Quick preview
  %(prog)s -s topic.json -w 4 --narrate --subtitles         # Full pipeline, parallel

Formats: presentation, instagram_reel, instagram_square, linkedin,
         linkedin_square, youtube_short, tiktok
        """,
    )
    parser.add_argument("--storyboard", "-s", required=True, type=Path)
    parser.add_argument("--output", "-o", type=Path, default=None)
    parser.add_argument("--quality", "-q", choices=["low", "medium", "high"], default="high")
    parser.add_argument("--workers", "-w", type=int, default=1)
    parser.add_argument("--scenes", nargs="*", default=None)
    parser.add_argument("--gen-only", action="store_true")

    # Social media features
    parser.add_argument(
        "--format", "-f", default=None,
        choices=list(FORMATS.keys()),
        help="Output format (overrides storyboard meta.format)"
    )
    parser.add_argument("--narrate", action="store_true", help="Add AI voiceover")
    parser.add_argument("--subtitles", action="store_true", help="Burn in subtitles")
    parser.add_argument("--post-copy", action="store_true", help="Generate social media post copy")
    parser.add_argument(
        "--voice", default="aria",
        choices=["aria", "guy", "jenny", "davis", "andrew", "emma"],
    )
    parser.add_argument("--rate", default="-5%", help="Speech rate (default: -5%%)")

    args = parser.parse_args()
    t_start = time.time()

    # ── 1. Load and validate ──
    print(f"[manimator] Loading: {args.storyboard}")
    with open(args.storyboard) as f:
        raw = json.load(f)

    # Override format if specified on CLI
    if args.format:
        raw.setdefault("meta", {})["format"] = args.format
        fmt = FORMATS[args.format]
        raw["meta"]["resolution"] = [fmt.width, fmt.height]

    storyboard = Storyboard(**raw)
    fmt_name = storyboard.meta.format
    fmt = FORMATS.get(fmt_name, FORMATS["presentation"])
    print(f"[manimator] {len(storyboard.scenes)} scenes | "
          f"theme={storyboard.meta.color_theme} | "
          f"format={fmt.name} ({fmt.width}x{fmt.height})")

    # ── 2. Generate code ──
    gen_file = args.storyboard.with_suffix(".py")
    if gen_file == args.storyboard:
        gen_file = args.storyboard.parent / f"{args.storyboard.stem}_gen.py"

    all_class_names = generate(storyboard, gen_file)

    # Filter scenes
    if args.scenes:
        scene_ids = set(args.scenes)
        class_names = [cn for cn in all_class_names
                       if any(sid in cn for sid in scene_ids)]
        if not class_names:
            print(f"[manimator] ERROR: No matching scenes for {args.scenes}")
            sys.exit(1)
    else:
        class_names = all_class_names

    if args.gen_only:
        print(f"[manimator] Code at {gen_file}. Skipping render.")
        return

    # ── 3. Render ──
    t_render = time.time()
    print(f"[manimator] Rendering {len(class_names)} scenes "
          f"(quality={args.quality}, workers={args.workers})...")

    video_files = render_all(
        gen_file, class_names,
        quality=args.quality, workers=args.workers,
    )
    print(f"[manimator] Rendered in {time.time() - t_render:.1f}s")

    # ── 4. Narration + Subtitles ──
    if args.narrate or args.subtitles:
        from manimator.narration import (
            generate_narration_script, synthesize_audio,
            merge_audio_video, VOICES,
        )

        voice = VOICES.get(args.voice, args.voice)
        processed_files = []
        audio_dir = gen_file.parent / "media" / "audio"
        srt_dir = gen_file.parent / "media" / "srt"
        audio_dir.mkdir(parents=True, exist_ok=True)
        srt_dir.mkdir(parents=True, exist_ok=True)

        scene_map = {f"S{i:02d}_{s.id}": s for i, s in enumerate(storyboard.scenes)}

        for vf, cn in zip(video_files, class_names):
            scene_spec = scene_map.get(cn)
            if scene_spec is None:
                processed_files.append(vf)
                continue

            script = generate_narration_script(scene_spec.model_dump())
            if not script.strip():
                processed_files.append(vf)
                continue

            print(f"  [{cn}] \"{script[:50]}...\"")
            audio_path = audio_dir / f"{cn}.mp3"

            if args.subtitles:
                # Generate subtitles + audio together
                from manimator.subtitles import generate_subtitles, burn_subtitles
                srt_path = srt_dir / f"{cn}.srt"
                generate_subtitles(script, srt_path, audio_path,
                                   voice=voice, rate=args.rate)

                # Burn subtitles + merge audio
                sub_style = "social" if fmt.pacing == "fast" else "academic"
                output_sub = Path(vf).parent / f"{cn}_sub.webm"
                try:
                    burn_subtitles(Path(vf), srt_path, audio_path,
                                  output_sub, style=sub_style)
                    processed_files.append(str(output_sub))
                except RuntimeError as e:
                    print(f"  [{cn}] Subtitle burn failed: {e}")
                    # Fallback to narration only
                    synthesize_audio(script, audio_path, voice=voice, rate=args.rate)
                    narrated = Path(vf).parent / f"{cn}_narrated.webm"
                    try:
                        merge_audio_video(Path(vf), audio_path, narrated)
                        processed_files.append(str(narrated))
                    except RuntimeError:
                        processed_files.append(vf)
            else:
                # Narration only (no subtitles)
                try:
                    synthesize_audio(script, audio_path, voice=voice, rate=args.rate)
                    narrated = Path(vf).parent / f"{cn}_narrated.webm"
                    merge_audio_video(Path(vf), audio_path, narrated)
                    processed_files.append(str(narrated))
                except Exception as e:
                    print(f"  [{cn}] TTS/merge failed, using silent: {e}")
                    processed_files.append(vf)

        video_files = processed_files
        feature = "narration + subtitles" if args.subtitles else "narration"
        print(f"[manimator] {feature.capitalize()} complete")

    # ── 5. Concatenate ──
    output = args.output
    if output is None:
        suffix = f"_{fmt_name}" if fmt_name != "presentation" else ""
        output = args.storyboard.parent / f"{args.storyboard.stem}{suffix}.webm"

    concatenate(video_files, output)
    file_size = output.stat().st_size / (1024 * 1024)

    # ── 6. Post copy ──
    if args.post_copy:
        post = generate_post_copy(raw, fmt_name)
        copy_file = output.with_suffix(".txt")
        with open(copy_file, "w") as f:
            f.write(f"=== {fmt.name} Post Copy ===\n\n")
            f.write(post["caption"])
            f.write(f"\n\n=== Hook Text ===\n{post['hook_text']}\n")
        print(f"[manimator] Post copy saved: {copy_file}")

    total = time.time() - t_start
    print(f"[manimator] Done! {output} ({file_size:.1f} MB) in {total:.0f}s")


if __name__ == "__main__":
    main()
