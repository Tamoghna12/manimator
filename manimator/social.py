"""
Social media format profiles and post generation.

Supports Instagram Reels, LinkedIn, YouTube Shorts, and TikTok formats.
"""

from dataclasses import dataclass


@dataclass
class FormatProfile:
    name: str
    width: int
    height: int
    frame_width: float    # Manim scene units
    frame_height: float   # Manim scene units
    max_duration: int     # seconds
    optimal_duration: int # seconds
    font_scale: float     # multiplier for base font sizes
    spacing_scale: float  # multiplier for spacing
    pacing: str           # "fast", "medium", "slow"


FORMATS = {
    "linkedin": FormatProfile(
        name="LinkedIn Video",
        width=1920, height=1080,
        frame_width=19.2, frame_height=10.8,
        max_duration=120, optimal_duration=60,
        font_scale=1.0, spacing_scale=1.0,
        pacing="medium",
    ),
    "linkedin_square": FormatProfile(
        name="LinkedIn Square",
        width=1080, height=1080,
        frame_width=10.8, frame_height=10.8,
        max_duration=120, optimal_duration=60,
        font_scale=1.1, spacing_scale=0.8,
        pacing="medium",
    ),
    "presentation": FormatProfile(
        name="Presentation (16:9)",
        width=1920, height=1080,
        frame_width=19.2, frame_height=10.8,
        max_duration=600, optimal_duration=180,
        font_scale=1.0, spacing_scale=1.0,
        pacing="slow",
    ),
}

# Pacing configs — control animation timing per format
PACING = {
    "fast": {
        "title_fade": 0.6,
        "element_fade": 0.2,
        "group_fade": 0.3,
        "scene_pause": 0.5,
        "transition": 0.15,
        "bullet_delay": 0.1,
    },
    "medium": {
        "title_fade": 1.0,
        "element_fade": 0.4,
        "group_fade": 0.6,
        "scene_pause": 1.2,
        "transition": 0.3,
        "bullet_delay": 0.18,
    },
    "slow": {
        "title_fade": 1.5,
        "element_fade": 0.5,
        "group_fade": 0.8,
        "scene_pause": 2.0,
        "transition": 0.4,
        "bullet_delay": 0.22,
    },
}

# Social-optimized font sizes (larger, bolder for mobile)
SOCIAL_FONTS = {
    "fast": {
        "section_header": 48,
        "scene_title": 44,
        "card_title": 36,
        "body_text": 30,
        "stat_value": 56,
        "stat_label": 24,
        "table_header": 26,
        "table_cell": 22,
        "footnote": 20,
        "hook_text": 52,
    },
    "medium": {
        "section_header": 40,
        "scene_title": 36,
        "card_title": 30,
        "body_text": 24,
        "stat_value": 48,
        "stat_label": 20,
        "table_header": 22,
        "table_cell": 20,
        "footnote": 18,
        "hook_text": 44,
    },
    "slow": {
        "section_header": 36,
        "scene_title": 32,
        "card_title": 26,
        "body_text": 22,
        "stat_value": 42,
        "stat_label": 18,
        "table_header": 20,
        "table_cell": 18,
        "footnote": 16,
        "hook_text": 40,
    },
}


def _extract_content(scenes: list) -> dict:
    """Extract structured content from all scene types."""
    hook_text = ""
    key_points = []
    stats = []
    references = []

    for scene in scenes:
        stype = scene["type"]
        if stype == "hook":
            hook_text = scene.get("hook_text", "")
        elif stype == "title":
            if not hook_text:
                hook_text = scene.get("subtitle", scene.get("title", ""))
        elif stype == "bullet_list":
            for item in scene.get("items", [])[:3]:
                key_points.append(item)
        elif stype == "bar_chart":
            bars = scene.get("bars", [])
            for b in bars[:3]:
                label = b["label"].replace("\n", " ")
                suffix = scene.get("value_suffix", "")
                stats.append(f"{label}: {b['value']}{suffix}")
        elif stype == "flowchart":
            stages = [s["label"].replace("\n", " ") for s in scene.get("stages", [])]
            if stages:
                key_points.append("Process: " + " → ".join(stages))
        elif stype == "two_panel":
            key_points.append(f"{scene.get('left_title', '')} vs {scene.get('right_title', '')}")
        elif stype == "closing":
            references = scene.get("references", [])

        if scene.get("callout"):
            key_points.append(scene["callout"])

    return {
        "hook": hook_text,
        "key_points": key_points,
        "stats": stats,
        "references": references,
    }


def generate_post_copy(storyboard_data: dict, platform: str) -> dict:
    """Generate platform-specific post copy from storyboard content."""
    meta = storyboard_data["meta"]
    scenes = storyboard_data["scenes"]
    title = meta["title"]
    branding = meta.get("branding") or {}
    custom_cta = branding.get("cta_text", "")

    content = _extract_content(scenes)
    key_points = content["key_points"]
    stats = content["stats"]
    references = content["references"]

    # Build hook line
    hook = content["hook"] or (key_points[0] if key_points else title)

    # Generate hashtags from title
    words = title.lower().replace("-", "").replace(":", "").split()
    stop_words = {"the", "a", "an", "in", "of", "and", "or", "to", "for",
                  "is", "how", "what", "why", "from", "with"}
    hashtags = [f"#{w}" for w in words if w not in stop_words and len(w) > 2]

    if platform in ("instagram_reel", "instagram_square", "tiktok", "youtube_short"):
        caption = f"{hook}\n\n"
        caption += f"{title}\n\n"
        if key_points:
            for kp in key_points[:4]:
                caption += f"-> {kp}\n"
            caption += "\n"
        if stats:
            for s in stats[:3]:
                caption += f"{s}\n"
            caption += "\n"
        caption += f"{custom_cta or 'Follow for more science content!'}\n\n"
        hashtags.extend(["#science", "#research", "#education", "#learnontiktok"])
        caption += " ".join(hashtags[:15])

        return {
            "caption": caption,
            "hashtags": hashtags,
            "hook_text": hook[:80],
        }

    if platform in ("linkedin", "linkedin_square"):
        post = f"{hook}\n\n"
        post += f"I put together a visual explainer on {title.lower()}.\n\n"
        if key_points:
            post += "Key takeaways:\n"
            for i, kp in enumerate(key_points[:5], 1):
                post += f"{i}. {kp}\n"
            post += "\n"
        if stats:
            post += "By the numbers:\n"
            for s in stats:
                post += f"  {s}\n"
            post += "\n"
        if references:
            post += "Based on:\n"
            for ref in references[:4]:
                post += f"  {ref}\n"
            post += "\n"
        post += f"{custom_cta or 'What aspect should I cover next?'}\n\n"
        hashtags.extend(["#science", "#research", "#datascience"])
        post += " ".join(hashtags[:8])

        return {
            "caption": post,
            "hashtags": hashtags,
            "hook_text": hook[:120],
        }

    return {"caption": title, "hashtags": [], "hook_text": title}
