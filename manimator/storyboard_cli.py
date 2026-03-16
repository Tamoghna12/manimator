#!/usr/bin/env python3
"""
Storyboard authoring CLI — scaffold, validate, and preview storyboards.

Usage:
    # List available templates and structures
    python -m manimator.storyboard_cli list

    # Generate an LLM prompt for a topic
    python -m manimator.storyboard_cli prompt "How CRISPR works" --domain biology_reel

    # Scaffold a blank storyboard from a structure
    python -m manimator.storyboard_cli scaffold --structure social_reel --topic "My Topic" -o my_video.json

    # Get a complete example storyboard
    python -m manimator.storyboard_cli example --domain cs_reel -o transformers_reel.json

    # Validate an existing storyboard
    python -m manimator.storyboard_cli validate my_video.json

    # Show schema reference for a scene type
    python -m manimator.storyboard_cli schema bar_chart
"""

import argparse
import json
import sys
from pathlib import Path

from manimator.schema import Storyboard
from manimator.topic_templates import (
    STRUCTURES, DOMAIN_TEMPLATES, SCENE_SCHEMAS,
    get_storyboard_prompt, list_structures, list_domains,
    get_example_storyboard,
)


def cmd_list(args):
    """List available structures and domain templates."""
    print(list_structures())
    print()
    print(list_domains())
    print()
    print("Color themes: wong (default), npg (Nature), tol_bright (presentations)")
    print()
    print("Scene types:", ", ".join(SCENE_SCHEMAS.keys()))


def cmd_prompt(args):
    """Generate an LLM prompt for creating a storyboard."""
    prompt = get_storyboard_prompt(
        topic=args.topic,
        structure=args.structure,
        domain=args.domain,
        format_type=args.format,
        theme=args.theme,
    )
    if args.output:
        Path(args.output).write_text(prompt)
        print(f"Prompt saved to {args.output}")
    else:
        print(prompt)


def cmd_scaffold(args):
    """Generate a blank storyboard JSON with the right structure."""
    struct_key = args.structure
    if args.domain and args.domain in DOMAIN_TEMPLATES:
        dt = DOMAIN_TEMPLATES[args.domain]
        struct_key = dt["structure"]
        theme = dt.get("theme", args.theme)
    else:
        theme = args.theme

    struct = STRUCTURES.get(struct_key, STRUCTURES["explainer"])
    scenes = []

    for i, s in enumerate(struct["scenes"]):
        schema = SCENE_SCHEMAS.get(s["type"], {})
        example = schema.get("example", {})

        # Create a skeleton scene with placeholder values
        scene = {"type": s["type"], "id": f"scene_{i}"}

        if s["type"] == "hook":
            scene["hook_text"] = f"TODO: Hook text for {args.topic}"
            scene["subtitle"] = "TODO: Subtitle"
        elif s["type"] == "title":
            scene["title"] = args.topic or "TODO: Title"
            scene["subtitle"] = "TODO: Subtitle"
        elif s["type"] == "bullet_list":
            scene["header"] = s.get("purpose", "TODO: Header")
            scene["items"] = ["TODO: Point 1", "TODO: Point 2", "TODO: Point 3"]
            scene["callout"] = "TODO: Key takeaway"
        elif s["type"] == "flowchart":
            scene["header"] = s.get("purpose", "TODO: Header")
            scene["stages"] = [
                {"label": "Step 1", "color_key": "blue"},
                {"label": "Step 2", "color_key": "green"},
                {"label": "Step 3", "color_key": "orange"},
            ]
            scene["callout"] = "TODO: Key takeaway"
        elif s["type"] == "two_panel":
            scene["header"] = s.get("purpose", "TODO: Comparison")
            scene["left_title"] = "TODO: Option A"
            scene["left_items"] = ["TODO: Point 1", "TODO: Point 2"]
            scene["right_title"] = "TODO: Option B"
            scene["right_items"] = ["TODO: Point 1", "TODO: Point 2"]
        elif s["type"] == "comparison_table":
            scene["header"] = s.get("purpose", "TODO: Comparison")
            scene["columns"] = ["Feature", "A", "B", "C"]
            scene["rows"] = [["TODO", "TODO", "TODO", "TODO"]]
        elif s["type"] == "bar_chart":
            scene["header"] = s.get("purpose", "TODO: Chart")
            scene["bars"] = [
                {"label": "Item A", "value": 80, "color_key": "blue"},
                {"label": "Item B", "value": 60, "color_key": "green"},
                {"label": "Item C", "value": 45, "color_key": "orange"},
            ]
            scene["value_suffix"] = "%"
            scene["callout"] = "TODO: Key takeaway"
        elif s["type"] == "scatter_plot":
            scene["header"] = s.get("purpose", "TODO: Scatter")
            scene["clusters"] = [
                {"label": "Group A", "center": [2.0, 1.5], "n": 20, "spread": 0.5, "color_key": "blue"},
                {"label": "Group B", "center": [-1.5, -1.0], "n": 20, "spread": 0.5, "color_key": "red"},
            ]
            scene["axes"] = ["X Axis", "Y Axis"]
        elif s["type"] == "equation":
            scene["header"] = s.get("purpose", "TODO: Equation")
            scene["latex"] = "y = f(x)"
            scene["explanation"] = "TODO: Explain the equation"
        elif s["type"] == "pipeline_diagram":
            scene["header"] = s.get("purpose", "TODO: Pipeline")
            scene["left_track"] = {"label": "Input A", "sublabel": "TODO"}
            scene["right_track"] = {"label": "Input B", "sublabel": "TODO"}
            scene["center_block"] = {"label": "Process", "items": ["Step 1", "Step 2"]}
        elif s["type"] == "closing":
            scene["id"] = "refs"
            scene["title"] = "Key References"
            scene["references"] = ["TODO: Author et al. (Year) Journal"]

        scenes.append(scene)

    # Determine format/resolution
    is_portrait = args.format in ("instagram_reel", "tiktok", "youtube_short")
    resolution = [1080, 1920] if is_portrait else (
        [1080, 1080] if args.format == "instagram_square" else [1920, 1080]
    )

    storyboard = {
        "meta": {
            "title": args.topic or "TODO: Title",
            "color_theme": theme,
            "format": args.format,
            "resolution": resolution,
        },
        "scenes": scenes,
    }

    output = args.output or f"{args.topic.lower().replace(' ', '_')[:30]}.json"
    Path(output).write_text(json.dumps(storyboard, indent=2))
    print(f"Scaffold saved to {output}")
    print(f"Structure: {struct_key} ({struct['description']})")
    print(f"Scenes: {len(scenes)}")
    print(f"Fill in the TODO fields, then render with:")
    if is_portrait:
        print(f"  python -m manimator.portrait -s {output} --narrate")
    else:
        print(f"  python -m manimator.orchestrator -s {output} --narrate")


def cmd_example(args):
    """Output a complete example storyboard."""
    example = get_example_storyboard(args.domain)
    output_str = json.dumps(example, indent=2)

    if args.output:
        Path(args.output).write_text(output_str)
        print(f"Example saved to {args.output}")
    else:
        print(output_str)


def cmd_validate(args):
    """Validate a storyboard JSON file against the schema."""
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    try:
        with open(path) as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        sys.exit(1)

    try:
        sb = Storyboard(**raw)
        print(f"Valid storyboard: {sb.meta.title}")
        print(f"  Scenes: {len(sb.scenes)}")
        print(f"  Theme: {sb.meta.color_theme}")
        print(f"  Format: {sb.meta.format}")
        for i, scene in enumerate(sb.scenes):
            sd = scene.model_dump()
            print(f"  [{i}] {sd['type']:20s} id={sd['id']}")
    except Exception as e:
        print(f"Validation failed: {e}")
        sys.exit(1)


def cmd_generate(args):
    """Generate a storyboard using an LLM provider."""
    from manimator.llm import generate_storyboard

    try:
        result = generate_storyboard(
            topic=args.topic,
            provider=args.provider,
            model=args.model,
            api_key=args.api_key,
            domain=args.domain,
            structure=args.structure,
            format_type=args.format,
            theme=args.theme,
            base_url=args.base_url or "",
        )
    except Exception as e:
        print(f"Generation failed: {e}")
        sys.exit(1)

    output_str = json.dumps(result, indent=2)
    output_path = args.output
    if output_path:
        Path(output_path).write_text(output_str)
        print(f"Storyboard saved to {output_path}")
    else:
        print(output_str)

    print(f"Title: {result['meta']['title']}")
    print(f"Scenes: {len(result['scenes'])}")

    if args.render:
        is_portrait = result.get("meta", {}).get("format", "") in (
            "instagram_reel", "tiktok", "youtube_short"
        )
        if not output_path:
            output_path = "generated_storyboard.json"
            Path(output_path).write_text(output_str)

        video_out = Path(output_path).stem + ".webm"
        module = "manimator.portrait" if is_portrait else "manimator.orchestrator"
        cmd = ["python", "-m", module, "-s", output_path, "-o", video_out]
        if is_portrait:
            cmd.extend(["--format", result["meta"].get("format", "instagram_reel")])
        print(f"Rendering: {' '.join(cmd)}")

        import subprocess
        proc = subprocess.run(cmd, capture_output=False)
        if proc.returncode == 0:
            print(f"Video saved to {video_out}")
        else:
            print("Render failed")
            sys.exit(1)


def cmd_upload(args):
    """Upload a rendered video to YouTube."""
    from manimator.uploader import upload_short, upload_video

    video_path = args.video_file
    if not Path(video_path).exists():
        print(f"Video file not found: {video_path}")
        sys.exit(1)

    if args.storyboard:
        sb_path = Path(args.storyboard)
        if not sb_path.exists():
            print(f"Storyboard not found: {sb_path}")
            sys.exit(1)
        with open(sb_path) as f:
            storyboard_data = json.load(f)
        result = upload_short(
            video_path=video_path,
            storyboard_data=storyboard_data,
            privacy=args.privacy,
        )
    else:
        title = args.title or Path(video_path).stem
        result = upload_video(
            video_path=video_path,
            title=title,
            privacy=args.privacy,
        )

    print(f"Uploaded: {result['url']}")
    print(f"Video ID: {result['video_id']}")
    print(f"Status: {result['status']}")


def cmd_pipeline(args):
    """Pipeline sub-subcommand dispatcher."""
    from manimator.pipeline import Pipeline

    pipe = Pipeline()
    try:
        if args.pipeline_cmd == "add-topics":
            path = Path(args.topics_file)
            if not path.exists():
                print(f"File not found: {path}")
                sys.exit(1)

            topics = []
            for line in path.read_text().strip().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    topics.append({
                        "topic": line,
                        "domain": args.domain,
                        "structure": args.structure,
                        "format": args.format,
                        "theme": args.theme,
                    })

            ids = pipe.add_topics(topics)
            print(f"Added {len(ids)} topics")

        elif args.pipeline_cmd == "add-storyboards":
            from manimator.schema import Storyboard

            entries = []
            for sb_path in args.storyboard_files:
                p = Path(sb_path)
                if not p.exists():
                    print(f"File not found: {p}")
                    continue
                if p.is_dir():
                    json_files = sorted(p.glob("*.json"))
                else:
                    json_files = [p]

                for jf in json_files:
                    try:
                        with open(jf) as f:
                            sb = json.load(f)
                        Storyboard(**sb)  # validate
                        entries.append({
                            "storyboard": sb,
                            "domain": args.domain,
                        })
                    except Exception as e:
                        print(f"Skipping {jf}: {e}")

            if entries:
                ids = pipe.add_storyboards(entries)
                print(f"Imported {len(ids)} storyboards (ready to render)")
            else:
                print("No valid storyboards found")

        elif args.pipeline_cmd == "render":
            results = pipe.run_renders(
                limit=args.limit,
                upload=args.upload,
                privacy=args.privacy,
                narrate=args.narrate,
                voice=args.voice,
                music=args.music,
            )
            done = sum(1 for r in results if r["status"] == "done")
            failed = sum(1 for r in results if r["status"] == "failed")
            print(f"Render complete: {done} done, {failed} failed out of {len(results)}")
            for r in results:
                print(f"  [{r['status']:8s}] {r['topic']}")

        elif args.pipeline_cmd == "run":
            results = pipe.run_pipeline(
                provider=args.provider,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url or "",
                limit=args.limit,
                upload=args.upload,
                privacy=args.privacy,
                narrate=args.narrate,
                voice=args.voice,
                music=args.music,
            )
            done = sum(1 for r in results if r["status"] == "done")
            failed = sum(1 for r in results if r["status"] == "failed")
            print(f"Pipeline complete: {done} done, {failed} failed out of {len(results)}")
            for r in results:
                print(f"  [{r['status']:8s}] {r['topic']}")

        elif args.pipeline_cmd == "import-csv":
            from manimator.pipeline import parse_csv
            from collections import Counter

            path = Path(args.csv_file)
            if not path.exists():
                print(f"File not found: {path}")
                sys.exit(1)

            topics, errors = parse_csv(path.read_text(encoding="utf-8", errors="replace"))

            if not topics:
                print("No valid topics found in CSV")
                sys.exit(1)

            # Summary table
            col_w = min(60, max((len(t["topic"]) for t in topics), default=10))
            header = f"  {'#':>4}  {'Topic':<{col_w}}  {'Category':<16}  {'Format':<18}  {'Voice':<8}  {'Pri':>3}"
            print(header)
            print("  " + "-" * (len(header) - 2))
            for i, t in enumerate(topics, 1):
                cat = t.get("category", "")
                print(f"  {i:>4}  {t['topic']:<{col_w}}  {cat:<16}  {t['format']:<18}  {t['voice']:<8}  {t['priority']:>3}")

            if errors:
                print(f"\n  Warnings on {len(errors)} row(s):")
                for e in errors:
                    for w in e.get("warnings", []):
                        print(f"    row {e['row']} ({e['topic'][:40]}): {w}")

            cats = Counter(t.get("category") or "(none)" for t in topics)
            print(f"\n  {len(topics)} topics across {len(cats)} categories:")
            for cat, n in sorted(cats.items()):
                print(f"    {cat}: {n}")

            if args.dry_run:
                print("\n  [Dry run — nothing added]")
            else:
                ids = pipe.add_topics(topics)
                print(f"\n  Added {len(ids)} topics to pipeline queue.")
                if args.run:
                    print("  Starting pipeline run…")
                    results = pipe.run_pipeline(
                        provider=args.provider,
                        model=args.model,
                        api_key=args.api_key,
                        limit=len(ids),
                        narrate=args.narrate,
                        voice=args.voice,
                    )
                    done = sum(1 for r in results if r["status"] == "done")
                    failed = sum(1 for r in results if r["status"] == "failed")
                    print(f"  Complete: {done} done, {failed} failed")

        elif args.pipeline_cmd == "status":
            status = pipe.get_status()
            print("Pipeline status:")
            for key in ("queued", "generating", "rendering", "uploading", "done", "failed", "total"):
                print(f"  {key:12s}: {status[key]}")

        elif args.pipeline_cmd == "list":
            videos = pipe.list_videos(status=args.status, limit=args.limit)
            if not videos:
                print("No videos found")
            else:
                for v in videos:
                    yt = f" → {v['youtube_url']}" if v.get("youtube_url") else ""
                    print(f"  [{v['status']:10s}] {v['topic']}{yt}")

        else:
            print("Unknown pipeline command. Use: add-topics, run, status, list")
    finally:
        pipe.close()


def cmd_analytics(args):
    """Analytics sub-subcommand dispatcher."""
    from manimator.analytics import Analytics

    analytics = Analytics()
    try:
        if args.analytics_cmd == "sync":
            count = analytics.sync_metrics(days=args.days)
            print(f"Synced {count} metric rows")

        elif args.analytics_cmd == "top":
            top = analytics.get_top_videos(metric=args.metric, limit=args.limit, days=args.days)
            if not top:
                print("No data available")
            else:
                for i, v in enumerate(top, 1):
                    metric_key = f"total_{args.metric}"
                    print(f"  {i}. {v.get('topic', 'Unknown')} — {v[metric_key]} {args.metric}")

        elif args.analytics_cmd == "insights":
            insights = analytics.get_insights()
            print("Analytics Insights:")
            print(f"  Total videos:   {insights['total_videos']}")
            print(f"  Total views:    {insights['total_views']}")
            print(f"  Avg views/vid:  {insights['avg_views_per_video']:.1f}")
            print(f"  Avg CTR:        {insights['avg_ctr']:.2%}")
            print(f"  Best domain:    {insights['best_domain']}")
            print(f"  Worst domain:   {insights['worst_domain']}")
            print(f"  Best post day:  {insights['best_posting_day']}")
            if insights["best_video"]:
                print(f"  Best video:     {insights['best_video']['topic']} "
                      f"({insights['best_video']['total_views']} views)")
            print(f"  Data freshness: {insights['data_freshness']}")

        else:
            print("Unknown analytics command. Use: sync, top, insights")
    finally:
        analytics.close()


def cmd_schema(args):
    """Show detailed schema for a scene type."""
    stype = args.scene_type
    if stype not in SCENE_SCHEMAS:
        print(f"Unknown scene type: {stype}")
        print(f"Available: {', '.join(SCENE_SCHEMAS.keys())}")
        sys.exit(1)

    info = SCENE_SCHEMAS[stype]
    print(f"Scene type: {stype}")
    print(f"Description: {info['description']}")
    print(f"\nFields:")
    for field, desc in info["fields"].items():
        print(f"  {field:15s} — {desc}")
    print(f"\nExample:")
    print(json.dumps(info["example"], indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Storyboard authoring tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # list
    sub.add_parser("list", help="List structures and domain templates")

    # prompt
    p_prompt = sub.add_parser("prompt", help="Generate LLM prompt for a topic")
    p_prompt.add_argument("topic", help="Video topic")
    p_prompt.add_argument("--structure", "-s", default="explainer")
    p_prompt.add_argument("--domain", "-d", default=None)
    p_prompt.add_argument("--format", "-f", default="presentation")
    p_prompt.add_argument("--theme", "-t", default="wong")
    p_prompt.add_argument("--output", "-o", default=None)

    # scaffold
    p_scaffold = sub.add_parser("scaffold", help="Generate blank storyboard JSON")
    p_scaffold.add_argument("--topic", required=True)
    p_scaffold.add_argument("--structure", "-s", default="explainer")
    p_scaffold.add_argument("--domain", "-d", default=None)
    p_scaffold.add_argument("--format", "-f", default="presentation")
    p_scaffold.add_argument("--theme", "-t", default="wong")
    p_scaffold.add_argument("--output", "-o", default=None)

    # example
    p_example = sub.add_parser("example", help="Get a complete example storyboard")
    p_example.add_argument("--domain", "-d", default="biology_reel")
    p_example.add_argument("--output", "-o", default=None)

    # validate
    p_validate = sub.add_parser("validate", help="Validate storyboard JSON")
    p_validate.add_argument("file", help="Path to storyboard JSON")

    # schema
    p_schema = sub.add_parser("schema", help="Show schema for a scene type")
    p_schema.add_argument("scene_type", help="Scene type name")

    # generate
    p_gen = sub.add_parser("generate", help="Generate storyboard using an LLM")
    p_gen.add_argument("topic", help="Video topic")
    p_gen.add_argument("--provider", "-p", default="openai",
                       help="LLM provider (openai, anthropic, google, zhipuai, openai_compatible)")
    p_gen.add_argument("--model", "-m", default=None, help="Model name (uses provider default)")
    p_gen.add_argument("--api-key", default=None, help="API key (falls back to env var)")
    p_gen.add_argument("--domain", "-d", default=None, help="Domain template")
    p_gen.add_argument("--structure", "-s", default="explainer", help="Story structure")
    p_gen.add_argument("--format", "-f", default="presentation", help="Video format")
    p_gen.add_argument("--theme", "-t", default="wong", help="Color theme")
    p_gen.add_argument("--base-url", default=None, help="Base URL for openai_compatible provider")
    p_gen.add_argument("--output", "-o", default=None, help="Output JSON file path")
    p_gen.add_argument("--render", action="store_true", help="Auto-render after generation")

    # upload
    p_upload = sub.add_parser("upload", help="Upload video to YouTube")
    p_upload.add_argument("video_file", help="Path to video file")
    p_upload.add_argument("--storyboard", "-s", default=None, help="Storyboard JSON for metadata")
    p_upload.add_argument("--title", default=None, help="Video title (if no storyboard)")
    p_upload.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])

    # pipeline
    p_pipe = sub.add_parser("pipeline", help="Batch pipeline operations")
    pipe_sub = p_pipe.add_subparsers(dest="pipeline_cmd")

    p_pipe_csv = pipe_sub.add_parser(
        "import-csv", help="Bulk-import topics from a CSV file (one row per video)"
    )
    p_pipe_csv.add_argument("csv_file", help="CSV file (columns: topic, category, domain, structure, format, theme, voice, priority)")
    p_pipe_csv.add_argument("--dry-run", action="store_true", help="Preview without adding to queue")
    p_pipe_csv.add_argument("--run", action="store_true", help="Immediately run pipeline after import")
    p_pipe_csv.add_argument("--provider", "-p", default="openai", help="LLM provider (used with --run)")
    p_pipe_csv.add_argument("--model", "-m", default=None, help="Model name (used with --run)")
    p_pipe_csv.add_argument("--api-key", default=None, help="API key (used with --run)")
    p_pipe_csv.add_argument("--narrate", action="store_true", help="Add narration (used with --run)")
    p_pipe_csv.add_argument("--voice", default="aria", help="Fallback voice if not set per-row")

    p_pipe_add = pipe_sub.add_parser("add-topics", help="Add topics from a text file")
    p_pipe_add.add_argument("topics_file", help="Text file with one topic per line")
    p_pipe_add.add_argument("--domain", "-d", default=None)
    p_pipe_add.add_argument("--structure", "-s", default="social_reel")
    p_pipe_add.add_argument("--format", "-f", default="instagram_reel")
    p_pipe_add.add_argument("--theme", "-t", default="wong")

    p_pipe_addsb = pipe_sub.add_parser("add-storyboards",
                                       help="Import pre-written storyboard JSONs (no LLM needed)")
    p_pipe_addsb.add_argument("storyboard_files", nargs="+",
                              help="JSON file(s) or directory of JSON files")
    p_pipe_addsb.add_argument("--domain", "-d", default=None)

    p_pipe_render = pipe_sub.add_parser("render", help="Render queued storyboards (no LLM needed)")
    p_pipe_render.add_argument("--limit", type=int, default=5)
    p_pipe_render.add_argument("--upload", action="store_true")
    p_pipe_render.add_argument("--privacy", default="private",
                               choices=["private", "unlisted", "public"])
    p_pipe_render.add_argument("--narrate", action="store_true")
    p_pipe_render.add_argument("--voice", default="aria")
    p_pipe_render.add_argument("--music", default="")

    p_pipe_run = pipe_sub.add_parser("run", help="Run the full pipeline (requires LLM API key)")
    p_pipe_run.add_argument("--provider", "-p", default="openai")
    p_pipe_run.add_argument("--model", "-m", default=None)
    p_pipe_run.add_argument("--api-key", default=None)
    p_pipe_run.add_argument("--base-url", default=None)
    p_pipe_run.add_argument("--limit", type=int, default=5)
    p_pipe_run.add_argument("--upload", action="store_true")
    p_pipe_run.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    p_pipe_run.add_argument("--narrate", action="store_true")
    p_pipe_run.add_argument("--voice", default="aria")
    p_pipe_run.add_argument("--music", default="")

    pipe_sub.add_parser("status", help="Show pipeline status")

    p_pipe_list = pipe_sub.add_parser("list", help="List videos")
    p_pipe_list.add_argument("--status", default=None)
    p_pipe_list.add_argument("--limit", type=int, default=20)

    # analytics
    p_anl = sub.add_parser("analytics", help="YouTube analytics operations")
    anl_sub = p_anl.add_subparsers(dest="analytics_cmd")

    p_anl_sync = anl_sub.add_parser("sync", help="Sync metrics from YouTube")
    p_anl_sync.add_argument("--days", type=int, default=7)

    p_anl_top = anl_sub.add_parser("top", help="Show top videos by metric")
    p_anl_top.add_argument("--metric", default="views", choices=["views", "likes", "comments", "shares"])
    p_anl_top.add_argument("--limit", type=int, default=10)
    p_anl_top.add_argument("--days", type=int, default=30)

    anl_sub.add_parser("insights", help="Show analytics insights summary")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    cmds = {
        "list": cmd_list,
        "prompt": cmd_prompt,
        "scaffold": cmd_scaffold,
        "example": cmd_example,
        "validate": cmd_validate,
        "schema": cmd_schema,
        "generate": cmd_generate,
        "upload": cmd_upload,
        "pipeline": cmd_pipeline,
        "analytics": cmd_analytics,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
