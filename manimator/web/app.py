#!/usr/bin/env python3
"""
manimator Web UI — Flask app for storyboard editing and video rendering.

Usage:
    python -m manimator.web.app
    # Opens at http://localhost:5100
"""

import html as html_mod
import json
import logging
import re
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import (
    Flask, render_template_string, request, jsonify,
    send_file,
)

from manimator.schema import Storyboard
from manimator.config import THEMES
from manimator.topic_templates import (
    STRUCTURES, DOMAIN_TEMPLATES, SCENE_SCHEMAS,
    get_storyboard_prompt, get_example_storyboard,
)
from manimator.portrait.html_scenes import render_scene_html

log = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static")

# ── Security ──
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB max request

# ── Bounded render pool (max 2 concurrent renders) ──
_render_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="render")

# In-memory job tracking
JOBS = {}
MAX_JOBS = 20
WORK_DIR = Path("manimator_output")
WORK_DIR.mkdir(exist_ok=True)

# Allowed values for user-controlled parameters
ALLOWED_FORMATS = {"instagram_reel", "tiktok", "youtube_short", "instagram_square",
                   "linkedin", "linkedin_square", "presentation"}
ALLOWED_VOICES = {"aria", "guy", "jenny", "davis", "andrew", "emma"}


def _sanitize_text(text: str, max_len: int = 500) -> str:
    """Strip HTML and limit length for user-provided text."""
    return html_mod.escape(str(text)[:max_len])


def _evict_old_jobs():
    """Remove oldest completed jobs when over limit."""
    if len(JOBS) <= MAX_JOBS:
        return
    finished = [(k, v) for k, v in JOBS.items() if v["status"] != "running"]
    finished.sort(key=lambda x: x[1].get("started", 0))
    for job_id, _ in finished[:len(JOBS) - MAX_JOBS]:
        del JOBS[job_id]


# ── API Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/templates", methods=["GET"])
def api_templates():
    """Return available structures, domains, themes, and scene schemas."""
    return jsonify({
        "structures": {k: v["description"] for k, v in STRUCTURES.items()},
        "domains": {
            k: {
                "description": v["description"],
                "structure": v["structure"],
                "theme": v.get("theme", "wong"),
                "example_topics": v.get("example_topics", []),
            }
            for k, v in DOMAIN_TEMPLATES.items()
        },
        "themes": list(THEMES.keys()),
        "scene_types": {k: v["description"] for k, v in SCENE_SCHEMAS.items()},
        "scene_schemas": {
            k: {"fields": v["fields"], "example": v["example"]}
            for k, v in SCENE_SCHEMAS.items()
        },
    })


@app.route("/api/example/<domain>", methods=["GET"])
def api_example(domain):
    """Return a complete example storyboard."""
    if domain not in DOMAIN_TEMPLATES:
        return jsonify({"error": f"Unknown domain: {domain}"}), 404
    return jsonify(get_example_storyboard(domain))


@app.route("/api/scaffold", methods=["POST"])
def api_scaffold():
    """Generate a scaffold storyboard from structure + topic."""
    data = request.json
    topic = data.get("topic", "Untitled")
    domain = data.get("domain")
    structure = data.get("structure", "explainer")
    theme = data.get("theme", "wong")
    fmt = data.get("format", "instagram_reel")

    if domain and domain in DOMAIN_TEMPLATES:
        dt = DOMAIN_TEMPLATES[domain]
        structure = dt["structure"]
        theme = dt.get("theme", theme)

    struct = STRUCTURES.get(structure, STRUCTURES["explainer"])
    scenes = []

    for i, s in enumerate(struct["scenes"]):
        schema = SCENE_SCHEMAS.get(s["type"], {})
        example = schema.get("example", {})
        scene = dict(example)
        scene["id"] = f"scene_{i}"

        if s["type"] == "title":
            scene["title"] = topic
            scene["subtitle"] = ""
        elif s["type"] == "hook":
            scene["hook_text"] = f"Did you know about {topic}?"
            scene["subtitle"] = f"Here's how {topic} works"

        scenes.append(scene)

    is_portrait = fmt in ("instagram_reel", "tiktok", "youtube_short")
    resolution = [1080, 1920] if is_portrait else [1920, 1080]

    return jsonify({
        "meta": {
            "title": topic,
            "color_theme": theme,
            "format": fmt,
            "resolution": resolution,
        },
        "scenes": scenes,
    })


@app.route("/api/validate", methods=["POST"])
def api_validate():
    """Validate a storyboard JSON."""
    try:
        sb = Storyboard(**request.json)
        return jsonify({"valid": True, "scenes": len(sb.scenes), "title": sb.meta.title})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)}), 400


@app.route("/api/preview_scene", methods=["POST"])
def api_preview_scene():
    """Render a single scene to HTML for live preview."""
    data = request.json
    scene_data = data.get("scene", {})
    theme_name = data.get("theme", "wong")
    theme = THEMES.get(theme_name, THEMES["wong"])

    html = render_scene_html(scene_data, theme)
    if not html:
        return jsonify({"error": f"Unknown scene type: {scene_data.get('type')}"}), 400

    return jsonify({"html": html})


@app.route("/api/prompt", methods=["POST"])
def api_prompt():
    """Generate an LLM prompt for storyboard creation."""
    data = request.json
    prompt = get_storyboard_prompt(
        topic=data.get("topic", ""),
        structure=data.get("structure", "explainer"),
        domain=data.get("domain"),
        format_type=data.get("format", "instagram_reel"),
        theme=data.get("theme", "wong"),
    )
    return jsonify({"prompt": prompt})


@app.route("/api/render", methods=["POST"])
def api_render():
    """Start a render job (runs in bounded thread pool)."""
    data = request.json
    storyboard = data.get("storyboard")
    fmt = data.get("format", "instagram_reel")
    narrate = bool(data.get("narrate", False))
    voice = data.get("voice", "aria")

    if not storyboard:
        return jsonify({"error": "No storyboard provided"}), 400

    # Validate format and voice against allow-lists
    if fmt not in ALLOWED_FORMATS:
        return jsonify({"error": f"Invalid format: {fmt}"}), 400
    if voice not in ALLOWED_VOICES:
        return jsonify({"error": f"Invalid voice: {voice}"}), 400

    # Check concurrent job limit
    running = sum(1 for j in JOBS.values() if j["status"] == "running")
    if running >= 2:
        return jsonify({"error": "Too many concurrent renders. Please wait."}), 429

    # Validate storyboard schema
    try:
        Storyboard(**storyboard)
    except Exception as e:
        return jsonify({"error": f"Invalid storyboard: {e}"}), 400

    _evict_old_jobs()

    job_id = str(uuid.uuid4())[:8]
    json_path = WORK_DIR / f"{job_id}.json"
    output_path = WORK_DIR / f"{job_id}.webm"

    with open(json_path, "w") as f:
        json.dump(storyboard, f, indent=2)

    JOBS[job_id] = {"status": "running", "started": time.time(), "output": None, "log": ""}

    def run_render():
        try:
            is_portrait = fmt in ("instagram_reel", "tiktok", "youtube_short", "instagram_square")
            module = "manimator.portrait" if is_portrait else "manimator.orchestrator"
            cmd = [
                "python", "-m", module,
                "-s", str(json_path),
                "-o", str(output_path),
            ]
            if is_portrait:
                cmd.extend(["--format", fmt])
            else:
                cmd.extend(["-q", "low"])
            if narrate:
                cmd.extend(["--narrate", "--voice", voice])

            log.info("Render started: job=%s format=%s narrate=%s", job_id, fmt, narrate)
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(Path.cwd()), timeout=600,  # 10 min timeout
            )
            JOBS[job_id]["log"] = result.stdout + result.stderr

            if result.returncode == 0 and output_path.exists():
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["output"] = str(output_path)
                JOBS[job_id]["size_mb"] = output_path.stat().st_size / (1024 * 1024)
                log.info("Render done: job=%s size=%.1fMB", job_id, JOBS[job_id]["size_mb"])
            else:
                JOBS[job_id]["status"] = "failed"
                JOBS[job_id]["error"] = result.stderr[-500:] if result.stderr else "Unknown error"
                log.error("Render failed: job=%s error=%s", job_id, JOBS[job_id]["error"][:200])
        except subprocess.TimeoutExpired:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = "Render timed out after 10 minutes"
            log.error("Render timeout: job=%s", job_id)
        except Exception as e:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(e)[:500]
            log.exception("Render crashed: job=%s", job_id)

    _render_pool.submit(run_render)

    return jsonify({"job_id": job_id, "status": "running"})


@app.route("/api/job/<job_id>", methods=["GET"])
def api_job_status(job_id):
    """Check render job status."""
    if not re.match(r'^[a-f0-9]{8}$', job_id):
        return jsonify({"error": "Invalid job ID"}), 400
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/download/<job_id>", methods=["GET"])
def api_download(job_id):
    """Download rendered video."""
    if not re.match(r'^[a-f0-9]{8}$', job_id):
        return jsonify({"error": "Invalid job ID"}), 400
    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Not ready"}), 404
    output = Path(job["output"])
    if not output.exists() or not output.resolve().is_relative_to(WORK_DIR.resolve()):
        return jsonify({"error": "File not found"}), 404
    return send_file(output, mimetype="video/webm", as_attachment=True,
                     download_name=f"manimator_{job_id}.webm")


# ── HTML Template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>manimator — Scientific Video Generator</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg: #0a0b10;
    --bg-raised: #12131a;
    --bg-card: #181a24;
    --bg-card-hover: #1e2030;
    --bg-input: #232736;
    --border: #272b3f;
    --border-subtle: #1f2234;
    --border-focus: #5b6abf;
    --text: #e8eaf4;
    --text-secondary: #c0c4d8;
    --text-muted: #6e7490;
    --accent: #6c7bf0;
    --accent-hover: #8b97f5;
    --accent-dim: rgba(108,123,240,0.12);
    --accent-glow: rgba(108,123,240,0.25);
    --green: #34d399;
    --green-dim: rgba(52,211,153,0.12);
    --orange: #f59e0b;
    --orange-dim: rgba(245,158,11,0.12);
    --red: #ef4444;
    --red-dim: rgba(239,68,68,0.12);
    --purple: #a78bfa;
    --purple-dim: rgba(167,139,250,0.12);
    --cyan: #22d3ee;
    --cyan-dim: rgba(34,211,238,0.12);
    --pink: #f472b6;
    --pink-dim: rgba(244,114,182,0.12);
    --radius: 12px;
    --radius-sm: 8px;
    --radius-lg: 16px;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 16px rgba(0,0,0,0.4);
    --shadow-lg: 0 8px 32px rgba(0,0,0,0.5);
    --transition: 0.2s cubic-bezier(0.4,0,0.2,1);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
}

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* ── Layout ── */
.app { display: flex; height: 100vh; }

.sidebar {
    width: 400px;
    background: var(--bg-raised);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    flex-shrink: 0;
}

.main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.toolbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 24px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-raised);
}

.editor-area {
    flex: 1;
    display: flex;
    overflow: hidden;
}

.json-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--border);
}

.preview-panel {
    width: 340px;
    display: flex;
    flex-direction: column;
    background: var(--bg-raised);
    flex-shrink: 0;
}

/* ── Sidebar Header ── */
.sidebar-header {
    padding: 20px 24px 16px;
    border-bottom: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(108,123,240,0.06) 0%, transparent 100%);
}

.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
}

.sidebar-brand .logo {
    width: 32px; height: 32px;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--accent), var(--purple));
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; font-weight: 800; color: white;
    box-shadow: 0 2px 8px var(--accent-glow);
}

.sidebar-header h1 {
    font-size: 18px;
    font-weight: 800;
    letter-spacing: -0.3px;
    background: linear-gradient(135deg, var(--accent), var(--purple));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.sidebar-header .tagline {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 2px;
    letter-spacing: 0.3px;
}

/* ── Tab Bar ── */
.tab-bar {
    display: flex;
    gap: 0;
    padding: 0;
    border-bottom: 1px solid var(--border);
    background: var(--bg-raised);
}

.tab {
    flex: 1;
    padding: 11px 8px;
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: var(--transition);
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    user-select: none;
}

.tab:hover { color: var(--text-secondary); background: rgba(255,255,255,0.02); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); background: var(--accent-dim); }

/* ── Sidebar Content ── */
.sidebar-content {
    flex: 1;
    overflow-y: auto;
    padding: 0;
}

.sidebar-section {
    padding: 16px 20px 8px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    gap: 8px;
}

.sidebar-section::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border-subtle);
}

/* ── Template Cards ── */
.template-grid {
    padding: 4px 12px;
}

.template-card {
    padding: 14px 16px;
    border-radius: var(--radius);
    cursor: pointer;
    margin-bottom: 4px;
    transition: var(--transition);
    border: 1px solid transparent;
    position: relative;
}

.template-card:hover {
    background: var(--bg-card-hover);
    border-color: var(--border);
}
.template-card.active {
    background: var(--accent-dim);
    border-color: var(--accent);
}

.template-card .tc-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 4px;
}

.template-card .tc-icon {
    width: 28px; height: 28px;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px;
    flex-shrink: 0;
}

.template-card .tc-name {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: -0.1px;
}

.template-card .tc-desc {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 2px;
    line-height: 1.5;
    padding-left: 38px;
}

.template-card .tc-meta {
    display: flex;
    gap: 6px;
    margin-top: 8px;
    padding-left: 38px;
}

.tc-tag {
    font-size: 9px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Domain-specific colors */
.domain-bio .tc-icon { background: var(--green-dim); color: var(--green); }
.domain-bio .tc-tag { background: var(--green-dim); color: var(--green); }
.domain-cs .tc-icon { background: var(--accent-dim); color: var(--accent); }
.domain-cs .tc-tag { background: var(--accent-dim); color: var(--accent); }
.domain-math .tc-icon { background: var(--orange-dim); color: var(--orange); }
.domain-math .tc-tag { background: var(--orange-dim); color: var(--orange); }
.domain-gen .tc-icon { background: var(--purple-dim); color: var(--purple); }
.domain-gen .tc-tag { background: var(--purple-dim); color: var(--purple); }

/* ── Quick Start ── */
.quick-start {
    padding: 16px 16px 8px;
}

.quick-start-inner {
    padding: 16px;
    border-radius: var(--radius);
    background: var(--bg-card);
    border: 1px solid var(--border);
}

/* ── Structure Cards (horizontal scroll) ── */
.structure-scroll {
    display: flex;
    gap: 8px;
    padding: 4px 16px 12px;
    overflow-x: auto;
    scroll-snap-type: x mandatory;
}

.structure-card {
    flex: 0 0 180px;
    padding: 14px;
    border-radius: var(--radius);
    background: var(--bg-card);
    border: 1px solid var(--border);
    cursor: pointer;
    transition: var(--transition);
    scroll-snap-align: start;
}

.structure-card:hover {
    border-color: var(--accent);
    background: var(--accent-dim);
    transform: translateY(-1px);
}

.structure-card .sc-name {
    font-size: 12px;
    font-weight: 700;
    margin-bottom: 4px;
    text-transform: capitalize;
}

.structure-card .sc-desc {
    font-size: 10px;
    color: var(--text-muted);
    line-height: 1.4;
}

.structure-card .sc-scenes {
    margin-top: 8px;
    display: flex;
    gap: 3px;
    flex-wrap: wrap;
}

.structure-card .sc-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--accent);
    opacity: 0.5;
}

/* ── Example Cards ── */
.example-cards {
    padding: 4px 12px 12px;
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
}

.example-card {
    padding: 14px 12px;
    border-radius: var(--radius);
    background: var(--bg-card);
    border: 1px solid var(--border);
    cursor: pointer;
    transition: var(--transition);
    text-align: center;
}

.example-card:hover {
    border-color: var(--green);
    background: var(--green-dim);
    transform: translateY(-1px);
}

.example-card .ec-icon {
    font-size: 20px;
    margin-bottom: 6px;
}

.example-card .ec-name {
    font-size: 11px;
    font-weight: 600;
}

.example-card .ec-tag {
    font-size: 9px;
    color: var(--green);
    margin-top: 4px;
    font-weight: 600;
}

/* ── Scene List ── */
.scene-list-header {
    padding: 10px 16px;
    display: flex;
    gap: 6px;
    border-bottom: 1px solid var(--border-subtle);
}

.scene-list {
    padding: 8px 12px;
    overflow-y: auto;
    flex: 1;
}

.scene-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    margin-bottom: 2px;
    transition: var(--transition);
    font-size: 13px;
    border: 1px solid transparent;
}

.scene-item:hover { background: var(--bg-card-hover); border-color: var(--border); }
.scene-item.active { background: var(--accent-dim); border-color: var(--accent); }

.scene-num {
    font-size: 10px;
    font-weight: 700;
    width: 22px; height: 22px;
    border-radius: 6px;
    background: var(--bg-input);
    display: flex; align-items: center; justify-content: center;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    flex-shrink: 0;
}

.scene-item.active .scene-num { background: var(--accent); color: white; }

.scene-badge {
    font-size: 9px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 4px;
    background: var(--bg-input);
    font-family: 'JetBrains Mono', monospace;
    white-space: nowrap;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
}

.scene-label {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 12px;
}

.scene-actions {
    display: flex;
    gap: 2px;
    opacity: 0;
    transition: opacity 0.15s;
}

.scene-item:hover .scene-actions { opacity: 1; }

.scene-empty {
    text-align: center;
    padding: 40px 20px;
    color: var(--text-muted);
    font-size: 12px;
    line-height: 1.6;
}

/* ── Buttons ── */
.btn {
    padding: 8px 16px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: var(--bg-input);
    color: var(--text);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
    font-family: 'Inter', sans-serif;
    white-space: nowrap;
    user-select: none;
}

.btn:hover { border-color: var(--border-focus); background: var(--bg-card-hover); }
.btn:active { transform: scale(0.97); }

.btn-primary {
    background: var(--accent);
    border-color: var(--accent);
    color: white;
    box-shadow: 0 2px 8px var(--accent-glow);
}

.btn-primary:hover { background: var(--accent-hover); box-shadow: 0 4px 12px var(--accent-glow); }

.btn-sm { padding: 5px 12px; font-size: 11px; border-radius: 6px; }

.btn-icon {
    width: 26px; height: 26px;
    padding: 0;
    display: flex; align-items: center; justify-content: center;
    border-radius: 6px;
    font-size: 12px;
}

.btn-danger { color: var(--red); }
.btn-danger:hover { background: var(--red-dim); border-color: var(--red); }

.btn-ghost {
    background: transparent;
    border-color: transparent;
    color: var(--text-muted);
}
.btn-ghost:hover { color: var(--text); background: var(--bg-card-hover); }

/* ── Inputs ── */
.form-group { margin-bottom: 14px; }

.form-label {
    display: block;
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 5px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

input[type="text"], input[type="number"], select, textarea {
    width: 100%;
    padding: 9px 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: var(--bg-input);
    color: var(--text);
    font-size: 13px;
    font-family: 'Inter', sans-serif;
    transition: var(--transition);
}

input:focus, select:focus, textarea:focus {
    outline: none;
    border-color: var(--border-focus);
    box-shadow: 0 0 0 3px var(--accent-dim);
}

textarea {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    resize: vertical;
    line-height: 1.6;
}

/* ── JSON Editor ── */
.json-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.8px;
    background: var(--bg-raised);
}

#jsonEditor {
    flex: 1;
    width: 100%;
    padding: 16px;
    background: var(--bg);
    color: var(--text);
    border: none;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.7;
    resize: none;
    outline: none;
    tab-size: 2;
}

/* ── Preview ── */
.preview-header {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    display: flex;
    justify-content: space-between;
    align-items: center;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    background: var(--bg-raised);
}

.preview-frame {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    overflow: hidden;
    background: repeating-conic-gradient(var(--bg-card) 0% 25%, var(--bg) 0% 50%) 50% / 16px 16px;
}

.preview-frame iframe {
    width: 270px;
    height: 480px;
    border: 2px solid var(--border);
    border-radius: 16px;
    background: white;
    transform-origin: top center;
    box-shadow: var(--shadow-lg);
}

/* ── Render Panel ── */
.render-panel {
    padding: 16px 20px;
    border-top: 1px solid var(--border);
    background: var(--bg-raised);
}

.render-options {
    display: flex;
    gap: 12px;
    margin-bottom: 12px;
    align-items: center;
}

.render-status {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 8px;
}

.render-status.done { color: var(--green); font-weight: 600; }
.render-status.error { color: var(--red); }

.progress-bar {
    height: 3px;
    background: var(--bg-input);
    border-radius: 2px;
    margin-top: 10px;
    overflow: hidden;
}

.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--purple));
    border-radius: 2px;
    transition: width 0.3s;
    animation: indeterminate 1.8s ease-in-out infinite;
}

@keyframes indeterminate {
    0% { transform: translateX(-100%); width: 35%; }
    50% { width: 55%; }
    100% { transform: translateX(280%); width: 35%; }
}

/* ── Toggle Switch ── */
.toggle-label {
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    user-select: none;
    color: var(--text-secondary);
}

.toggle {
    position: relative;
    width: 36px; height: 20px;
    appearance: none; -webkit-appearance: none;
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 10px;
    cursor: pointer;
    transition: var(--transition);
}

.toggle::after {
    content: '';
    position: absolute;
    top: 2px; left: 2px;
    width: 14px; height: 14px;
    border-radius: 50%;
    background: var(--text-muted);
    transition: var(--transition);
}

.toggle:checked { background: var(--accent); border-color: var(--accent); }
.toggle:checked::after { left: 18px; background: white; }

/* ── Modal ── */
.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.7);
    backdrop-filter: blur(4px);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 100;
}

.modal-overlay.show { display: flex; }

.modal {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 28px;
    width: 90%;
    max-width: 760px;
    max-height: 85vh;
    overflow-y: auto;
    box-shadow: var(--shadow-lg);
}

.modal h2 {
    font-size: 18px;
    margin-bottom: 4px;
    font-weight: 700;
}

.modal .modal-subtitle {
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 16px;
}

/* ── Guide ── */
.guide-content {
    padding: 0 16px 16px;
}

.guide-section {
    margin-bottom: 24px;
}

.guide-section h3 {
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 12px;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
}

.guide-section h3 .step-num {
    width: 24px; height: 24px;
    border-radius: 8px;
    background: var(--accent);
    color: white;
    font-size: 12px;
    display: inline-flex; align-items: center; justify-content: center;
    font-weight: 700;
}

.guide-card {
    padding: 16px;
    border-radius: var(--radius);
    background: var(--bg-card);
    border: 1px solid var(--border);
    margin-bottom: 8px;
}

.guide-card p {
    font-size: 12px;
    color: var(--text-secondary);
    line-height: 1.7;
    margin-bottom: 8px;
}

.guide-card p:last-child { margin-bottom: 0; }

.guide-card code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 4px;
    background: var(--bg-input);
    color: var(--accent);
}

.guide-card .tip {
    display: flex;
    gap: 8px;
    align-items: flex-start;
    padding: 10px 12px;
    border-radius: 8px;
    background: var(--accent-dim);
    margin-top: 8px;
}

.guide-card .tip-icon { font-size: 14px; flex-shrink: 0; margin-top: 1px; }
.guide-card .tip p { margin: 0; font-size: 11px; color: var(--text-secondary); }

.workflow-steps {
    display: flex;
    gap: 0;
    position: relative;
    margin: 12px 0;
}

.workflow-step {
    flex: 1;
    text-align: center;
    padding: 12px 8px;
    position: relative;
}

.workflow-step::after {
    content: '';
    position: absolute;
    top: 28px; right: -8px;
    width: 16px; height: 2px;
    background: var(--border);
}

.workflow-step:last-child::after { display: none; }

.workflow-step .ws-icon {
    width: 36px; height: 36px;
    border-radius: 10px;
    margin: 0 auto 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px;
}

.workflow-step .ws-label {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Scene type reference grid */
.scene-ref-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    margin-top: 8px;
}

.scene-ref-item {
    padding: 8px 10px;
    border-radius: 6px;
    background: var(--bg-input);
    display: flex;
    align-items: center;
    gap: 8px;
}

.scene-ref-item .sri-name {
    font-size: 11px;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
}

.scene-ref-item .sri-desc {
    font-size: 10px;
    color: var(--text-muted);
}

/* ── Settings Section ── */
.settings-section {
    padding: 16px;
    margin: 8px 12px;
    border-radius: var(--radius);
    background: var(--bg-card);
    border: 1px solid var(--border);
}

.settings-section h4 {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    margin-bottom: 14px;
}

/* ── Add Scene Modal Grid ── */
.scene-type-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 16px;
}

.scene-type-card {
    padding: 14px 16px;
    border-radius: var(--radius);
    background: var(--bg-input);
    border: 1px solid var(--border);
    cursor: pointer;
    transition: var(--transition);
}

.scene-type-card:hover {
    border-color: var(--accent);
    background: var(--accent-dim);
    transform: translateY(-1px);
}

.scene-type-card .stc-name {
    font-size: 12px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 3px;
}

.scene-type-card .stc-desc {
    font-size: 10px;
    color: var(--text-muted);
    line-height: 1.4;
}

/* ── Toast ── */
.toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    padding: 12px 20px;
    border-radius: var(--radius);
    background: var(--bg-card);
    border: 1px solid var(--border);
    font-size: 13px;
    font-weight: 500;
    z-index: 200;
    opacity: 0;
    transform: translateY(10px);
    transition: all 0.3s;
    box-shadow: var(--shadow-md);
}

.toast.show { opacity: 1; transform: translateY(0); }
.toast.success { border-color: var(--green); color: var(--green); background: var(--bg-card); }
.toast.error { border-color: var(--red); color: var(--red); background: var(--bg-card); }

/* ── Toolbar Separator ── */
.toolbar-sep {
    width: 1px;
    height: 20px;
    background: var(--border);
}
</style>
</head>
<body>
<div class="app">
    <!-- ── Sidebar ── -->
    <div class="sidebar">
        <div class="sidebar-header">
            <div class="sidebar-brand">
                <div class="logo">M</div>
                <div>
                    <h1>manimator</h1>
                    <div class="tagline">Scientific Video Generator</div>
                </div>
            </div>
        </div>

        <div class="tab-bar">
            <div class="tab active" onclick="switchTab(this,'templates')">Templates</div>
            <div class="tab" onclick="switchTab(this,'scenes')">Scenes</div>
            <div class="tab" onclick="switchTab(this,'settings')">Settings</div>
            <div class="tab" onclick="switchTab(this,'guide')">Guide</div>
        </div>

        <!-- ════ Templates Tab ════ -->
        <div class="sidebar-content tab-content" id="tab-templates">

            <!-- Quick Start -->
            <div class="quick-start">
                <div class="quick-start-inner">
                    <div class="form-group" style="margin-bottom:10px">
                        <label class="form-label">Topic</label>
                        <input type="text" id="topicInput" placeholder="e.g., How CRISPR-Cas9 edits genes" />
                    </div>
                    <div style="display:flex;gap:8px">
                        <button class="btn btn-primary" onclick="scaffoldFromTopic()" style="flex:1">Generate Scaffold</button>
                        <button class="btn" onclick="showPromptModal()" title="Generate an LLM prompt to create storyboard JSON">LLM Prompt</button>
                    </div>
                </div>
            </div>

            <!-- Video Structures -->
            <div class="sidebar-section">Video Structures</div>
            <div class="structure-scroll" id="structureList"></div>

            <!-- Domain Templates — Biology -->
            <div class="sidebar-section">Biology</div>
            <div class="template-grid" id="domainBioList"></div>

            <!-- Domain Templates — Computer Science -->
            <div class="sidebar-section">Computer Science</div>
            <div class="template-grid" id="domainCsList"></div>

            <!-- Domain Templates — Mathematics -->
            <div class="sidebar-section">Mathematics</div>
            <div class="template-grid" id="domainMathList"></div>

            <!-- Domain Templates — General -->
            <div class="sidebar-section">General</div>
            <div class="template-grid" id="domainGenList"></div>

            <!-- Ready-to-Render Examples -->
            <div class="sidebar-section">Ready-to-Render Examples</div>
            <div class="example-cards" id="exampleList"></div>

        </div>

        <!-- ════ Scenes Tab ════ -->
        <div class="sidebar-content tab-content" id="tab-scenes" style="display:none">
            <div class="scene-list-header">
                <button class="btn btn-sm btn-primary" onclick="addScene()" style="flex:1">+ Add Scene</button>
                <button class="btn btn-sm btn-ghost" onclick="duplicateScene()" title="Duplicate selected scene">Dup</button>
            </div>
            <div class="scene-list" id="sceneList">
                <div class="scene-empty">
                    No scenes yet.<br>
                    Start by picking a template or adding scenes manually.
                </div>
            </div>
        </div>

        <!-- ════ Settings Tab ════ -->
        <div class="sidebar-content tab-content" id="tab-settings" style="display:none">
            <div class="settings-section">
                <h4>Project</h4>
                <div class="form-group">
                    <label class="form-label">Title</label>
                    <input type="text" id="metaTitle" onchange="updateMeta()" />
                </div>
                <div class="form-group">
                    <label class="form-label">Color Theme</label>
                    <select id="metaTheme" onchange="updateMeta()">
                        <option value="wong">Wong (Nature Methods default)</option>
                        <option value="npg">NPG (Nature Publishing Group)</option>
                        <option value="tol_bright">Tol Bright (high contrast)</option>
                    </select>
                </div>
            </div>
            <div class="settings-section">
                <h4>Output Format</h4>
                <div class="form-group">
                    <label class="form-label">Video Format</label>
                    <select id="metaFormat" onchange="updateMeta()">
                        <optgroup label="Portrait (HTML/CSS Engine)">
                            <option value="instagram_reel">Instagram Reel (1080x1920)</option>
                            <option value="tiktok">TikTok (1080x1920)</option>
                            <option value="youtube_short">YouTube Short (1080x1920)</option>
                        </optgroup>
                        <optgroup label="Landscape (Manim Engine)">
                            <option value="linkedin">LinkedIn (1920x1080)</option>
                            <option value="linkedin_square">LinkedIn Square (1080x1080)</option>
                            <option value="presentation">Presentation (1920x1080)</option>
                        </optgroup>
                    </select>
                </div>
            </div>
            <div class="settings-section">
                <h4>Narration</h4>
                <div class="form-group">
                    <label class="form-label">Voice</label>
                    <select id="metaVoice">
                        <optgroup label="Female">
                            <option value="aria">Aria (professional, clear)</option>
                            <option value="jenny">Jenny (warm, friendly)</option>
                            <option value="emma">Emma (British, clear)</option>
                        </optgroup>
                        <optgroup label="Male">
                            <option value="guy">Guy (professional, calm)</option>
                            <option value="davis">Davis (conversational)</option>
                            <option value="andrew">Andrew (authoritative)</option>
                        </optgroup>
                    </select>
                </div>
            </div>
        </div>

        <!-- ════ Guide Tab ════ -->
        <div class="sidebar-content tab-content" id="tab-guide" style="display:none">
            <div class="guide-content">
                <div class="guide-section" style="margin-top:16px">
                    <h3>How It Works</h3>
                    <div class="guide-card">
                        <div class="workflow-steps">
                            <div class="workflow-step">
                                <div class="ws-icon" style="background:var(--accent-dim);color:var(--accent)">1</div>
                                <div class="ws-label">Pick Template</div>
                            </div>
                            <div class="workflow-step">
                                <div class="ws-icon" style="background:var(--orange-dim);color:var(--orange)">2</div>
                                <div class="ws-label">Edit JSON</div>
                            </div>
                            <div class="workflow-step">
                                <div class="ws-icon" style="background:var(--purple-dim);color:var(--purple)">3</div>
                                <div class="ws-label">Preview</div>
                            </div>
                            <div class="workflow-step">
                                <div class="ws-icon" style="background:var(--green-dim);color:var(--green)">4</div>
                                <div class="ws-label">Render</div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="guide-section">
                    <h3><span class="step-num">1</span> Choose a Starting Point</h3>
                    <div class="guide-card">
                        <p><strong>Domain Templates</strong> give you a scaffold matching your field (biology, CS, math). Pick one, then fill in your content.</p>
                        <p><strong>Ready-to-Render Examples</strong> are complete storyboards you can render immediately to see what the output looks like.</p>
                        <p><strong>Video Structures</strong> define the scene sequence (explainer, reel, data-heavy, etc.) without domain-specific content.</p>
                        <div class="tip">
                            <span class="tip-icon">*</span>
                            <p>Enter a topic in the Quick Start box before clicking a domain template — the scaffold will use your topic.</p>
                        </div>
                    </div>
                </div>

                <div class="guide-section">
                    <h3><span class="step-num">2</span> Edit Your Storyboard</h3>
                    <div class="guide-card">
                        <p>The storyboard is a JSON document with two parts:</p>
                        <p><code>"meta"</code> — title, color theme, format, resolution</p>
                        <p><code>"scenes"</code> — an array of scene objects, each with a <code>"type"</code> field</p>
                        <p>Edit the JSON directly in the editor. Use the <strong>Scenes</strong> tab to reorder, add, or delete scenes. Changes sync both ways.</p>
                        <div class="tip">
                            <span class="tip-icon">*</span>
                            <p>Click <strong>LLM Prompt</strong> to generate a prompt you can paste into Claude or ChatGPT. The LLM will return valid storyboard JSON you can paste back.</p>
                        </div>
                    </div>
                </div>

                <div class="guide-section">
                    <h3><span class="step-num">3</span> Scene Types Reference</h3>
                    <div class="guide-card">
                        <p>Each scene type has specific fields. Use the <strong>+ Add Scene</strong> button to see all types with their defaults.</p>
                        <div class="scene-ref-grid">
                            <div class="scene-ref-item">
                                <span class="sri-name">hook</span>
                                <span class="sri-desc">Bold opener</span>
                            </div>
                            <div class="scene-ref-item">
                                <span class="sri-name">title</span>
                                <span class="sri-desc">Title card</span>
                            </div>
                            <div class="scene-ref-item">
                                <span class="sri-name">bullet_list</span>
                                <span class="sri-desc">Key points</span>
                            </div>
                            <div class="scene-ref-item">
                                <span class="sri-name">flowchart</span>
                                <span class="sri-desc">Process flow</span>
                            </div>
                            <div class="scene-ref-item">
                                <span class="sri-name">bar_chart</span>
                                <span class="sri-desc">Data bars</span>
                            </div>
                            <div class="scene-ref-item">
                                <span class="sri-name">scatter_plot</span>
                                <span class="sri-desc">XY clusters</span>
                            </div>
                            <div class="scene-ref-item">
                                <span class="sri-name">comparison_table</span>
                                <span class="sri-desc">Side-by-side</span>
                            </div>
                            <div class="scene-ref-item">
                                <span class="sri-name">two_panel</span>
                                <span class="sri-desc">Split view</span>
                            </div>
                            <div class="scene-ref-item">
                                <span class="sri-name">equation</span>
                                <span class="sri-desc">Math formula</span>
                            </div>
                            <div class="scene-ref-item">
                                <span class="sri-name">pipeline_diagram</span>
                                <span class="sri-desc">System arch</span>
                            </div>
                            <div class="scene-ref-item">
                                <span class="sri-name">closing</span>
                                <span class="sri-desc">References</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="guide-section">
                    <h3><span class="step-num">4</span> Preview &amp; Render</h3>
                    <div class="guide-card">
                        <p>The <strong>Preview</strong> panel shows a live HTML preview of each scene. Use the dropdown to switch between scenes.</p>
                        <p>Click <strong>Validate</strong> to check your JSON before rendering. The validator checks all required fields and types.</p>
                        <p>Click <strong>Render Video</strong> to generate the final video. Portrait formats use the HTML/CSS engine with frame-perfect animation capture. Landscape formats use Manim.</p>
                        <div class="tip">
                            <span class="tip-icon">*</span>
                            <p>Rendering takes 30s-3min depending on scene count and narration. The progress indicator will update until complete.</p>
                        </div>
                    </div>
                </div>

                <div class="guide-section">
                    <h3><span class="step-num">5</span> CLI Usage</h3>
                    <div class="guide-card">
                        <p>You can also use manimator from the command line:</p>
                        <p><code>python -m manimator.portrait -s story.json --narrate</code></p>
                        <p><code>python -m manimator.orchestrator -s story.json -q high</code></p>
                        <p><code>python -m manimator.storyboard_cli list</code></p>
                        <p><code>python -m manimator.storyboard_cli prompt "CRISPR" --domain biology_reel</code></p>
                    </div>
                </div>
            </div>
        </div>

        <!-- ════ Render ════ -->
        <div class="render-panel">
            <div class="render-options">
                <label class="toggle-label">
                    <input type="checkbox" class="toggle" id="cbNarrate" checked>
                    <span>Narrate</span>
                </label>
                <span style="flex:1"></span>
                <span style="font-size:11px;color:var(--text-muted)" id="renderEngineHint">Engine: HTML/CSS</span>
            </div>
            <button class="btn btn-primary" onclick="startRender()" id="renderBtn" style="width:100%">
                Render Video
            </button>
            <div class="render-status" id="renderStatus"></div>
            <div class="progress-bar" id="progressBar" style="display:none">
                <div class="progress-fill"></div>
            </div>
        </div>
    </div>

    <!-- ── Main Area ── -->
    <div class="main">
        <div class="toolbar">
            <span style="font-weight:700;font-size:14px;letter-spacing:-0.2px" id="toolbarTitle">Untitled</span>
            <span style="flex:1"></span>
            <button class="btn btn-sm" onclick="validateStoryboard()">Validate</button>
            <div class="toolbar-sep"></div>
            <button class="btn btn-sm" onclick="downloadJson()">Export JSON</button>
            <button class="btn btn-sm" onclick="importJson()">Import JSON</button>
        </div>

        <div class="editor-area">
            <!-- JSON Editor -->
            <div class="json-panel">
                <div class="json-header">
                    <span>Storyboard JSON</span>
                    <div style="display:flex;gap:6px">
                        <button class="btn btn-sm" onclick="formatJson()">Format</button>
                    </div>
                </div>
                <textarea id="jsonEditor" spellcheck="false"></textarea>
            </div>

            <!-- Live Preview -->
            <div class="preview-panel">
                <div class="preview-header">
                    <span>Scene Preview</span>
                    <select id="previewScene" onchange="previewCurrentScene()" style="width:150px;padding:4px 8px;font-size:11px"></select>
                </div>
                <div class="preview-frame">
                    <iframe id="previewIframe" sandbox="allow-scripts"></iframe>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- LLM Prompt Modal -->
<div class="modal-overlay" id="promptModal">
    <div class="modal">
        <h2>LLM Prompt Generator</h2>
        <p class="modal-subtitle">
            Copy this prompt and paste it into Claude, ChatGPT, or any LLM. It will return valid storyboard JSON that you can paste into the editor.
        </p>
        <textarea id="promptText" rows="20" readonly style="font-size:11px"></textarea>
        <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end">
            <button class="btn" onclick="copyPrompt()">Copy to Clipboard</button>
            <button class="btn" onclick="closeModal('promptModal')">Close</button>
        </div>
    </div>
</div>

<!-- Add Scene Modal -->
<div class="modal-overlay" id="addSceneModal">
    <div class="modal">
        <h2>Add Scene</h2>
        <p class="modal-subtitle">Choose a scene type. It will be added with default values that you can edit in the JSON.</p>
        <div class="scene-type-grid" id="sceneTypeGrid"></div>
        <div style="margin-top:16px;text-align:right">
            <button class="btn" onclick="closeModal('addSceneModal')">Cancel</button>
        </div>
    </div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<!-- Hidden file input for import -->
<input type="file" id="fileInput" accept=".json" style="display:none" onchange="handleFileImport(event)" />

<script>
// ── State ──
let storyboard = {
    meta: { title: "Untitled", color_theme: "wong", format: "instagram_reel" },
    scenes: []
};
let templates = {};
let selectedSceneIdx = -1;
let currentJobId = null;

const DOMAIN_CATEGORIES = {
    bio: ['biology_mechanism', 'biology_reel'],
    cs: ['cs_algorithm', 'cs_reel'],
    math: ['math_concept', 'math_reel'],
    gen: ['paper_review'],
};

const DOMAIN_ICONS = {
    biology_mechanism: 'B', biology_reel: 'B',
    cs_algorithm: 'C', cs_reel: 'C',
    math_concept: 'M', math_reel: 'M',
    paper_review: 'P',
};

const EXAMPLE_ICONS = {
    biology_reel: 'DNA',
    cs_reel: '{ }',
    math_reel: 'f(x)',
};

// ── Init ──
async function init() {
    const resp = await fetch('/api/templates');
    templates = await resp.json();
    renderStructureList();
    renderDomainLists();
    renderExampleList();
    buildAddSceneModal();
    updateEngineHint();
    syncUI();
}

function renderStructureList() {
    const el = document.getElementById('structureList');
    el.innerHTML = '';
    for (const [key, val] of Object.entries(templates.structures || {})) {
        const sceneCount = val.match(/\d+/) || ['?'];
        el.innerHTML += `
            <div class="structure-card" onclick="scaffoldStructure('${key}')">
                <div class="sc-name">${key.replace(/_/g, ' ')}</div>
                <div class="sc-desc">${val}</div>
            </div>`;
    }
}

function renderDomainLists() {
    for (const [cat, domains] of Object.entries(DOMAIN_CATEGORIES)) {
        const el = document.getElementById(`domain${cat.charAt(0).toUpperCase()+cat.slice(1)}List`);
        if (!el) continue;
        el.innerHTML = '';
        for (const key of domains) {
            const info = templates.domains?.[key];
            if (!info) continue;
            const topics = (info.example_topics || []).slice(0, 3);
            el.innerHTML += `
                <div class="template-card domain-${cat}" onclick="loadDomainTemplate('${key}')">
                    <div class="tc-header">
                        <div class="tc-icon">${DOMAIN_ICONS[key] || '?'}</div>
                        <div class="tc-name">${key.replace(/_/g, ' ')}</div>
                    </div>
                    <div class="tc-desc">${info.description}</div>
                    <div class="tc-meta">
                        <span class="tc-tag">${info.structure}</span>
                        <span class="tc-tag">${info.theme}</span>
                    </div>
                </div>`;
        }
    }
}

function renderExampleList() {
    const el = document.getElementById('exampleList');
    el.innerHTML = '';
    for (const domain of ['biology_reel', 'cs_reel', 'math_reel']) {
        const label = domain.split('_')[0];
        el.innerHTML += `
            <div class="example-card" onclick="loadExample('${domain}')">
                <div class="ec-icon" style="font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:700;color:var(--green)">${EXAMPLE_ICONS[domain] || ''}</div>
                <div class="ec-name">${label}</div>
                <div class="ec-tag">RENDER READY</div>
            </div>`;
    }
}

function buildAddSceneModal() {
    const grid = document.getElementById('sceneTypeGrid');
    grid.innerHTML = '';
    for (const [key, desc] of Object.entries(templates.scene_types || {})) {
        grid.innerHTML += `
            <div class="scene-type-card" onclick="insertScene('${key}')">
                <div class="stc-name">${key}</div>
                <div class="stc-desc">${desc}</div>
            </div>`;
    }
}

// ── Template Loading ──
async function loadDomainTemplate(domain) {
    const topic = document.getElementById('topicInput').value || templates.domains[domain]?.example_topics?.[0] || 'Untitled';
    const fmt = document.getElementById('metaFormat').value;
    const resp = await fetch('/api/scaffold', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ topic, domain, format: fmt })
    });
    storyboard = await resp.json();
    syncUI();
    switchTab(document.querySelector('.tab'), 'templates');
    toast('Scaffold loaded — edit the JSON to fill in your content', 'success');
}

async function loadExample(domain) {
    const resp = await fetch(`/api/example/${domain}`);
    storyboard = await resp.json();
    syncUI();
    toast('Example loaded — ready to render!', 'success');
}

async function scaffoldFromTopic() {
    const topic = document.getElementById('topicInput').value;
    if (!topic) { toast('Enter a topic first', 'error'); return; }
    const fmt = document.getElementById('metaFormat').value;
    const resp = await fetch('/api/scaffold', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ topic, structure: 'social_reel', format: fmt })
    });
    storyboard = await resp.json();
    syncUI();
    toast('Scaffold generated from topic', 'success');
}

async function scaffoldStructure(structure) {
    const topic = document.getElementById('topicInput').value || 'Untitled';
    const fmt = document.getElementById('metaFormat').value;
    const resp = await fetch('/api/scaffold', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ topic, structure, format: fmt })
    });
    storyboard = await resp.json();
    syncUI();
    toast(`"${structure}" structure loaded`, 'success');
}

// ── Sync UI ──
function syncUI() {
    document.getElementById('jsonEditor').value = JSON.stringify(storyboard, null, 2);
    document.getElementById('toolbarTitle').textContent = storyboard.meta?.title || 'Untitled';
    document.getElementById('metaTitle').value = storyboard.meta?.title || '';
    document.getElementById('metaTheme').value = storyboard.meta?.color_theme || 'wong';
    document.getElementById('metaFormat').value = storyboard.meta?.format || 'instagram_reel';
    renderSceneList();
    updatePreviewDropdown();
    updateEngineHint();
    if (storyboard.scenes?.length > 0 && selectedSceneIdx < 0) {
        selectedSceneIdx = 0;
    }
    previewCurrentScene();
}

function syncFromJson() {
    try {
        storyboard = JSON.parse(document.getElementById('jsonEditor').value);
        document.getElementById('toolbarTitle').textContent = storyboard.meta?.title || 'Untitled';
        renderSceneList();
        updatePreviewDropdown();
        updateEngineHint();
    } catch(e) { /* ignore parse errors during typing */ }
}

function updateEngineHint() {
    const fmt = storyboard.meta?.format || document.getElementById('metaFormat').value;
    const isPortrait = ['instagram_reel','tiktok','youtube_short','instagram_square'].includes(fmt);
    const hint = document.getElementById('renderEngineHint');
    if (hint) hint.textContent = `Engine: ${isPortrait ? 'HTML/CSS' : 'Manim'}`;
}

// Debounced JSON sync
let syncTimer = null;
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('jsonEditor').addEventListener('input', () => {
        clearTimeout(syncTimer);
        syncTimer = setTimeout(syncFromJson, 500);
    });
    init();
});

function formatJson() {
    try {
        const obj = JSON.parse(document.getElementById('jsonEditor').value);
        document.getElementById('jsonEditor').value = JSON.stringify(obj, null, 2);
        storyboard = obj;
    } catch(e) { toast('Invalid JSON syntax', 'error'); }
}

// ── Scene List ──
function renderSceneList() {
    const el = document.getElementById('sceneList');
    const scenes = storyboard.scenes || [];
    if (scenes.length === 0) {
        el.innerHTML = '<div class="scene-empty">No scenes yet.<br>Start by picking a template or adding scenes manually.</div>';
        return;
    }
    el.innerHTML = '';
    scenes.forEach((scene, i) => {
        const active = i === selectedSceneIdx ? 'active' : '';
        const label = scene.header || scene.title || scene.hook_text || scene.id || '(unnamed)';
        el.innerHTML += `
            <div class="scene-item ${active}" onclick="selectScene(${i})">
                <span class="scene-num">${i+1}</span>
                <span class="scene-badge">${scene.type}</span>
                <span class="scene-label">${label.substring(0, 35)}</span>
                <div class="scene-actions">
                    <button class="btn btn-icon btn-sm btn-ghost" onclick="event.stopPropagation();moveScene(${i},-1)" title="Move up">&#x25B2;</button>
                    <button class="btn btn-icon btn-sm btn-ghost" onclick="event.stopPropagation();moveScene(${i},1)" title="Move down">&#x25BC;</button>
                    <button class="btn btn-icon btn-sm btn-danger" onclick="event.stopPropagation();deleteScene(${i})" title="Delete">&#x2715;</button>
                </div>
            </div>`;
    });
}

function selectScene(idx) {
    selectedSceneIdx = idx;
    renderSceneList();
    document.getElementById('previewScene').value = idx;
    previewCurrentScene();
}

function moveScene(idx, dir) {
    const scenes = storyboard.scenes;
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= scenes.length) return;
    [scenes[idx], scenes[newIdx]] = [scenes[newIdx], scenes[idx]];
    if (selectedSceneIdx === idx) selectedSceneIdx = newIdx;
    syncUI();
}

function deleteScene(idx) {
    storyboard.scenes.splice(idx, 1);
    if (selectedSceneIdx >= storyboard.scenes.length) selectedSceneIdx = storyboard.scenes.length - 1;
    syncUI();
}

function addScene() {
    document.getElementById('addSceneModal').classList.add('show');
}

function duplicateScene() {
    if (selectedSceneIdx < 0 || !storyboard.scenes?.[selectedSceneIdx]) {
        toast('Select a scene first', 'error');
        return;
    }
    const copy = JSON.parse(JSON.stringify(storyboard.scenes[selectedSceneIdx]));
    copy.id = copy.id + '_copy';
    storyboard.scenes.splice(selectedSceneIdx + 1, 0, copy);
    selectedSceneIdx++;
    syncUI();
    toast('Scene duplicated', 'success');
}

function insertScene(type) {
    const schema = templates.scene_schemas?.[type];
    const newScene = schema ? { ...schema.example, id: `${type}_${storyboard.scenes.length}` } : { type, id: `scene_${storyboard.scenes.length}` };
    storyboard.scenes.push(newScene);
    closeModal('addSceneModal');
    selectedSceneIdx = storyboard.scenes.length - 1;
    syncUI();
    // Auto-switch to scenes tab
    const scenesTab = document.querySelectorAll('.tab')[1];
    switchTab(scenesTab, 'scenes');
    toast(`Added ${type} scene`, 'success');
}

// ── Preview ──
function updatePreviewDropdown() {
    const sel = document.getElementById('previewScene');
    sel.innerHTML = '';
    (storyboard.scenes || []).forEach((s, i) => {
        const label = s.header || s.title || s.hook_text || s.id || `Scene ${i}`;
        sel.innerHTML += `<option value="${i}">${i+1}. ${label.substring(0, 25)}</option>`;
    });
    if (selectedSceneIdx >= 0) sel.value = selectedSceneIdx;
}

async function previewCurrentScene() {
    const idx = parseInt(document.getElementById('previewScene').value);
    if (isNaN(idx) || !storyboard.scenes?.[idx]) return;

    const resp = await fetch('/api/preview_scene', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            scene: storyboard.scenes[idx],
            theme: storyboard.meta?.color_theme || 'wong'
        })
    });

    if (resp.ok) {
        const data = await resp.json();
        const iframe = document.getElementById('previewIframe');
        iframe.srcdoc = data.html;
    }
}

// ── Meta Settings ──
function updateMeta() {
    storyboard.meta.title = document.getElementById('metaTitle').value;
    storyboard.meta.color_theme = document.getElementById('metaTheme').value;
    storyboard.meta.format = document.getElementById('metaFormat').value;
    document.getElementById('toolbarTitle').textContent = storyboard.meta.title;
    document.getElementById('jsonEditor').value = JSON.stringify(storyboard, null, 2);
    updateEngineHint();
    previewCurrentScene();
}

// ── Validate ──
async function validateStoryboard() {
    try {
        storyboard = JSON.parse(document.getElementById('jsonEditor').value);
    } catch(e) {
        toast('Invalid JSON syntax', 'error');
        return;
    }
    const resp = await fetch('/api/validate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(storyboard)
    });
    const data = await resp.json();
    if (data.valid) {
        toast(`Valid storyboard: "${data.title}" with ${data.scenes} scenes`, 'success');
    } else {
        toast(`Validation error: ${data.error}`, 'error');
    }
}

// ── Render ──
async function startRender() {
    try {
        storyboard = JSON.parse(document.getElementById('jsonEditor').value);
    } catch(e) {
        toast('Invalid JSON — fix before rendering', 'error');
        return;
    }

    const btn = document.getElementById('renderBtn');
    btn.disabled = true;
    btn.textContent = 'Rendering...';
    document.getElementById('progressBar').style.display = 'block';
    document.getElementById('renderStatus').textContent = 'Starting render...';
    document.getElementById('renderStatus').className = 'render-status';

    // Remove any existing download button
    const existingDl = document.querySelector('.render-panel .btn-dl');
    if (existingDl) existingDl.remove();

    const resp = await fetch('/api/render', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            storyboard,
            format: storyboard.meta?.format || 'instagram_reel',
            narrate: document.getElementById('cbNarrate').checked,
            voice: document.getElementById('metaVoice').value,
        })
    });
    const data = await resp.json();
    currentJobId = data.job_id;
    pollJob();
}

async function pollJob() {
    if (!currentJobId) return;
    const resp = await fetch(`/api/job/${currentJobId}`);
    const job = await resp.json();

    const status = document.getElementById('renderStatus');
    const btn = document.getElementById('renderBtn');

    if (job.status === 'running') {
        const elapsed = Math.round(Date.now()/1000 - job.started);
        status.textContent = `Rendering... (${elapsed}s elapsed)`;
        setTimeout(pollJob, 2000);
    } else if (job.status === 'done') {
        status.textContent = `Render complete — ${job.size_mb?.toFixed(1)} MB`;
        status.className = 'render-status done';
        btn.disabled = false;
        btn.textContent = 'Render Video';
        document.getElementById('progressBar').style.display = 'none';

        const dl = document.createElement('a');
        dl.href = `/api/download/${currentJobId}`;
        dl.className = 'btn btn-primary btn-dl';
        dl.style.cssText = 'display:inline-block;margin-top:10px;text-decoration:none;text-align:center;width:100%';
        dl.textContent = 'Download Video';
        status.after(dl);

        toast('Render complete!', 'success');
    } else {
        status.textContent = `Failed: ${job.error || 'Unknown error'}`;
        status.className = 'render-status error';
        btn.disabled = false;
        btn.textContent = 'Render Video';
        document.getElementById('progressBar').style.display = 'none';
        toast('Render failed — check logs', 'error');
    }
}

// ── LLM Prompt ──
async function showPromptModal() {
    const topic = document.getElementById('topicInput').value || storyboard.meta?.title || '';
    const fmt = document.getElementById('metaFormat').value;
    const theme = document.getElementById('metaTheme').value;

    const resp = await fetch('/api/prompt', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ topic, format: fmt, theme, structure: 'social_reel' })
    });
    const data = await resp.json();
    document.getElementById('promptText').value = data.prompt;
    document.getElementById('promptModal').classList.add('show');
}

function copyPrompt() {
    navigator.clipboard.writeText(document.getElementById('promptText').value);
    toast('Copied to clipboard', 'success');
}

// ── Import/Export ──
function downloadJson() {
    try {
        const obj = JSON.parse(document.getElementById('jsonEditor').value);
        const blob = new Blob([JSON.stringify(obj, null, 2)], {type: 'application/json'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${(obj.meta?.title || 'storyboard').replace(/\s+/g, '_').toLowerCase()}.json`;
        a.click();
    } catch(e) { toast('Invalid JSON', 'error'); }
}

function importJson() {
    document.getElementById('fileInput').click();
}

function handleFileImport(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            storyboard = JSON.parse(e.target.result);
            syncUI();
            toast('Imported successfully', 'success');
        } catch(err) { toast('Invalid JSON file', 'error'); }
    };
    reader.readAsText(file);
    event.target.value = '';
}

// ── Tabs ──
function switchTab(el, tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
    el.classList.add('active');
    document.getElementById(`tab-${tab}`).style.display = '';
}

// ── Modal ──
function closeModal(id) {
    document.getElementById(id).classList.remove('show');
}

document.querySelectorAll('.modal-overlay').forEach(m => {
    m.addEventListener('click', (e) => { if (e.target === m) m.classList.remove('show'); });
});

// ── Toast ──
function toast(msg, type = '') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `toast show ${type}`;
    setTimeout(() => el.classList.remove('show'), 3500);
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import webbrowser
    port = 5100
    log.info("Starting web UI at http://localhost:%d", port)
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
