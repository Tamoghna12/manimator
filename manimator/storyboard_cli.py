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
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
