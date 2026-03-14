#!/usr/bin/env python3
"""
vidgen Web UI — Flask app for storyboard editing and video rendering.

Usage:
    python -m vidgen.web.app
    # Opens at http://localhost:5100
"""

import json
import subprocess
import threading
import time
import uuid
from pathlib import Path

from flask import (
    Flask, render_template_string, request, jsonify,
    send_file, send_from_directory,
)

from vidgen.schema import Storyboard
from vidgen.config import THEMES
from vidgen.topic_templates import (
    STRUCTURES, DOMAIN_TEMPLATES, SCENE_SCHEMAS,
    get_storyboard_prompt, get_example_storyboard,
)
from vidgen.portrait.html_scenes import render_scene_html

app = Flask(__name__, static_folder="static")

# In-memory job tracking
JOBS = {}
WORK_DIR = Path("vidgen_output")
WORK_DIR.mkdir(exist_ok=True)


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
    """Start a render job (runs in background)."""
    data = request.json
    storyboard = data.get("storyboard")
    fmt = data.get("format", "instagram_reel")
    narrate = data.get("narrate", False)
    voice = data.get("voice", "aria")

    if not storyboard:
        return jsonify({"error": "No storyboard provided"}), 400

    # Validate first
    try:
        Storyboard(**storyboard)
    except Exception as e:
        return jsonify({"error": f"Invalid storyboard: {e}"}), 400

    job_id = str(uuid.uuid4())[:8]
    json_path = WORK_DIR / f"{job_id}.json"
    output_path = WORK_DIR / f"{job_id}.webm"

    with open(json_path, "w") as f:
        json.dump(storyboard, f, indent=2)

    JOBS[job_id] = {"status": "running", "started": time.time(), "output": None, "log": ""}

    def run_render():
        is_portrait = fmt in ("instagram_reel", "tiktok", "youtube_short", "instagram_square")
        module = "vidgen.portrait" if is_portrait else "vidgen.orchestrator"
        cmd = [
            "python", "-m", module,
            "-s", str(json_path),
            "-o", str(output_path),
        ]
        if is_portrait:
            cmd.extend(["--format", fmt])
        else:
            cmd.extend(["-q", "low"])  # faster for landscape preview
        if narrate:
            cmd.extend(["--narrate", "--voice", voice])

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(Path.cwd()))
        JOBS[job_id]["log"] = result.stdout + result.stderr

        if result.returncode == 0 and output_path.exists():
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["output"] = str(output_path)
            JOBS[job_id]["size_mb"] = output_path.stat().st_size / (1024 * 1024)
        else:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = result.stderr[-500:] if result.stderr else "Unknown error"

    thread = threading.Thread(target=run_render, daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "status": "running"})


@app.route("/api/job/<job_id>", methods=["GET"])
def api_job_status(job_id):
    """Check render job status."""
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/download/<job_id>", methods=["GET"])
def api_download(job_id):
    """Download rendered video."""
    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Not ready"}), 404
    return send_file(job["output"], mimetype="video/webm", as_attachment=True,
                     download_name=f"vidgen_{job_id}.webm")


# ── HTML Template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>vidgen — Scientific Video Generator</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg: #0f1117;
    --bg-card: #1a1d27;
    --bg-input: #232736;
    --border: #2d3148;
    --border-focus: #5b6abf;
    --text: #e4e6f0;
    --text-muted: #8b8fa4;
    --accent: #6c7bf0;
    --accent-hover: #8b97f5;
    --green: #34d399;
    --orange: #f59e0b;
    --red: #ef4444;
    --radius: 12px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
}

/* ── Layout ── */
.app { display: flex; height: 100vh; }

.sidebar {
    width: 380px;
    background: var(--bg-card);
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
    gap: 12px;
    padding: 16px 24px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-card);
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
    width: 320px;
    display: flex;
    flex-direction: column;
    background: var(--bg-card);
    flex-shrink: 0;
}

/* ── Sidebar ── */
.sidebar-header {
    padding: 20px 20px 12px;
    border-bottom: 1px solid var(--border);
}

.sidebar-header h1 {
    font-size: 20px;
    font-weight: 800;
    background: linear-gradient(135deg, var(--accent), #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.sidebar-header p {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 4px;
}

.sidebar-section {
    padding: 16px 20px 8px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
}

.sidebar-content {
    flex: 1;
    overflow-y: auto;
    padding: 0 12px 12px;
}

.template-card {
    padding: 12px 14px;
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 4px;
    transition: background 0.15s;
}

.template-card:hover { background: var(--bg-input); }
.template-card.active { background: var(--border-focus); }

.template-card .tc-name {
    font-size: 13px;
    font-weight: 600;
}

.template-card .tc-desc {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 2px;
}

.template-card .tc-topics {
    font-size: 10px;
    color: var(--text-muted);
    margin-top: 4px;
    font-style: italic;
}

/* ── Scene List ── */
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
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 2px;
    transition: background 0.15s;
    font-size: 13px;
}

.scene-item:hover { background: var(--bg-input); }
.scene-item.active { background: var(--border-focus); }

.scene-badge {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 4px;
    background: var(--bg-input);
    font-family: 'JetBrains Mono', monospace;
    white-space: nowrap;
}

.scene-label {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.scene-actions {
    display: flex;
    gap: 4px;
    opacity: 0;
    transition: opacity 0.15s;
}

.scene-item:hover .scene-actions { opacity: 1; }

/* ── Buttons ── */
.btn {
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg-input);
    color: var(--text);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    font-family: 'Inter', sans-serif;
    white-space: nowrap;
}

.btn:hover { border-color: var(--border-focus); background: var(--border); }

.btn-primary {
    background: var(--accent);
    border-color: var(--accent);
    color: white;
}

.btn-primary:hover { background: var(--accent-hover); }

.btn-sm { padding: 4px 10px; font-size: 11px; border-radius: 6px; }

.btn-icon {
    width: 28px;
    height: 28px;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    font-size: 14px;
}

.btn-danger { color: var(--red); }
.btn-danger:hover { background: rgba(239,68,68,0.15); border-color: var(--red); }

/* ── Inputs ── */
.form-group {
    margin-bottom: 14px;
}

.form-label {
    display: block;
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

input[type="text"], input[type="number"], select, textarea {
    width: 100%;
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg-input);
    color: var(--text);
    font-size: 13px;
    font-family: 'Inter', sans-serif;
    transition: border-color 0.15s;
}

input:focus, select:focus, textarea:focus {
    outline: none;
    border-color: var(--border-focus);
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
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
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
    line-height: 1.6;
    resize: none;
    outline: none;
}

/* ── Preview ── */
.preview-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.preview-frame {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 12px;
    overflow: hidden;
}

.preview-frame iframe {
    width: 270px;
    height: 480px;
    border: 2px solid var(--border);
    border-radius: 12px;
    background: white;
    transform-origin: top center;
}

/* ── Render Panel ── */
.render-panel {
    padding: 16px 20px;
    border-top: 1px solid var(--border);
    background: var(--bg-card);
}

.render-options {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
    flex-wrap: wrap;
}

.render-status {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 8px;
}

.render-status.done { color: var(--green); }
.render-status.error { color: var(--red); }

.progress-bar {
    height: 4px;
    background: var(--bg-input);
    border-radius: 2px;
    margin-top: 8px;
    overflow: hidden;
}

.progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.3s;
    animation: indeterminate 1.5s ease-in-out infinite;
}

@keyframes indeterminate {
    0% { transform: translateX(-100%); width: 40%; }
    50% { width: 60%; }
    100% { transform: translateX(250%); width: 40%; }
}

/* ── Modal ── */
.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 100;
}

.modal-overlay.show { display: flex; }

.modal {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 24px;
    width: 90%;
    max-width: 700px;
    max-height: 80vh;
    overflow-y: auto;
}

.modal h2 {
    font-size: 18px;
    margin-bottom: 16px;
}

/* ── Tabs ── */
.tab-bar {
    display: flex;
    gap: 2px;
    padding: 0 12px;
    border-bottom: 1px solid var(--border);
}

.tab {
    padding: 10px 16px;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.15s;
}

.tab:hover { color: var(--text); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

/* ── Toast ── */
.toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    padding: 12px 20px;
    border-radius: 10px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    font-size: 13px;
    font-weight: 500;
    z-index: 200;
    opacity: 0;
    transform: translateY(10px);
    transition: all 0.3s;
}

.toast.show { opacity: 1; transform: translateY(0); }
.toast.success { border-color: var(--green); color: var(--green); }
.toast.error { border-color: var(--red); color: var(--red); }
</style>
</head>
<body>
<div class="app">
    <!-- ── Sidebar ── -->
    <div class="sidebar">
        <div class="sidebar-header">
            <h1>vidgen</h1>
            <p>Scientific Video Generator</p>
        </div>

        <div class="tab-bar">
            <div class="tab active" data-tab="templates" onclick="switchTab(this,'templates')">Templates</div>
            <div class="tab" data-tab="scenes" onclick="switchTab(this,'scenes')">Scenes</div>
            <div class="tab" data-tab="settings" onclick="switchTab(this,'settings')">Settings</div>
        </div>

        <!-- Templates Tab -->
        <div class="sidebar-content tab-content" id="tab-templates">
            <div class="sidebar-section">Quick Start</div>
            <div style="padding: 8px 8px 16px">
                <div class="form-group">
                    <label class="form-label">Topic</label>
                    <input type="text" id="topicInput" placeholder="e.g., How CRISPR works" />
                </div>
                <div style="display:flex;gap:8px">
                    <button class="btn btn-primary" onclick="scaffoldFromTopic()" style="flex:1">Generate Scaffold</button>
                    <button class="btn" onclick="showPromptModal()" title="Get LLM prompt">LLM</button>
                </div>
            </div>

            <div class="sidebar-section">Domain Templates</div>
            <div id="domainList"></div>

            <div class="sidebar-section">Examples</div>
            <div id="exampleList"></div>
        </div>

        <!-- Scenes Tab -->
        <div class="sidebar-content tab-content" id="tab-scenes" style="display:none">
            <div style="padding: 8px 8px 4px; display:flex; gap:6px">
                <button class="btn btn-sm" onclick="addScene()" style="flex:1">+ Add Scene</button>
            </div>
            <div class="scene-list" id="sceneList"></div>
        </div>

        <!-- Settings Tab -->
        <div class="sidebar-content tab-content" id="tab-settings" style="display:none">
            <div style="padding: 12px 8px">
                <div class="form-group">
                    <label class="form-label">Title</label>
                    <input type="text" id="metaTitle" onchange="updateMeta()" />
                </div>
                <div class="form-group">
                    <label class="form-label">Theme</label>
                    <select id="metaTheme" onchange="updateMeta()">
                        <option value="wong">Wong (Default)</option>
                        <option value="npg">NPG (Nature)</option>
                        <option value="tol_bright">Tol Bright</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Format</label>
                    <select id="metaFormat" onchange="updateMeta()">
                        <option value="instagram_reel">Instagram Reel (1080x1920)</option>
                        <option value="tiktok">TikTok (1080x1920)</option>
                        <option value="youtube_short">YouTube Short (1080x1920)</option>
                        <option value="linkedin">LinkedIn (1920x1080)</option>
                        <option value="linkedin_square">LinkedIn Square (1080x1080)</option>
                        <option value="presentation">Presentation (1920x1080)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Narration Voice</label>
                    <select id="metaVoice">
                        <option value="aria">Aria (Female, professional)</option>
                        <option value="guy">Guy (Male, professional)</option>
                        <option value="jenny">Jenny (Female, warm)</option>
                        <option value="davis">Davis (Male, conversational)</option>
                        <option value="andrew">Andrew (Male, authoritative)</option>
                        <option value="emma">Emma (Female, clear)</option>
                    </select>
                </div>
            </div>
        </div>

        <!-- Render -->
        <div class="render-panel">
            <div style="display:flex; gap:8px; align-items:center; margin-bottom:10px">
                <label style="font-size:12px; display:flex; align-items:center; gap:6px; cursor:pointer">
                    <input type="checkbox" id="cbNarrate" checked> Narrate
                </label>
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
            <span style="font-weight:700;font-size:14px" id="toolbarTitle">Untitled</span>
            <span style="flex:1"></span>
            <button class="btn btn-sm" onclick="validateStoryboard()">Validate</button>
            <button class="btn btn-sm" onclick="downloadJson()">Export JSON</button>
            <button class="btn btn-sm" onclick="importJson()">Import JSON</button>
        </div>

        <div class="editor-area">
            <!-- JSON Editor -->
            <div class="json-panel">
                <div class="json-header">
                    <span>STORYBOARD JSON</span>
                    <button class="btn btn-sm" onclick="formatJson()">Format</button>
                </div>
                <textarea id="jsonEditor" spellcheck="false"></textarea>
            </div>

            <!-- Live Preview -->
            <div class="preview-panel">
                <div class="preview-header">
                    <span>PREVIEW</span>
                    <select id="previewScene" onchange="previewCurrentScene()" style="width:140px;padding:4px 8px;font-size:11px"></select>
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
        <h2>LLM Prompt</h2>
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">
            Copy this prompt and paste it into Claude, ChatGPT, or any LLM to generate a storyboard.
        </p>
        <textarea id="promptText" rows="18" readonly style="font-size:11px"></textarea>
        <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
            <button class="btn" onclick="copyPrompt()">Copy to Clipboard</button>
            <button class="btn" onclick="closeModal('promptModal')">Close</button>
        </div>
    </div>
</div>

<!-- Add Scene Modal -->
<div class="modal-overlay" id="addSceneModal">
    <div class="modal">
        <h2>Add Scene</h2>
        <div id="sceneTypeGrid" style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px"></div>
        <div style="margin-top:12px;text-align:right">
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

// ── Init ──
async function init() {
    const resp = await fetch('/api/templates');
    templates = await resp.json();
    renderDomainList();
    renderExampleList();
    buildAddSceneModal();
    syncUI();
}

function renderDomainList() {
    const el = document.getElementById('domainList');
    el.innerHTML = '';
    for (const [key, val] of Object.entries(templates.domains)) {
        const topics = (val.example_topics || []).slice(0, 2).join(', ');
        el.innerHTML += `
            <div class="template-card" onclick="loadDomainTemplate('${key}')">
                <div class="tc-name">${key.replace(/_/g, ' ')}</div>
                <div class="tc-desc">${val.description}</div>
                ${topics ? `<div class="tc-topics">e.g., ${topics}</div>` : ''}
            </div>`;
    }
}

function renderExampleList() {
    const el = document.getElementById('exampleList');
    el.innerHTML = '';
    for (const domain of ['biology_reel', 'cs_reel', 'math_reel']) {
        const info = templates.domains[domain];
        el.innerHTML += `
            <div class="template-card" onclick="loadExample('${domain}')">
                <div class="tc-name">${domain.replace(/_/g, ' ')} (ready to render)</div>
                <div class="tc-desc">${info?.description || ''}</div>
            </div>`;
    }
}

function buildAddSceneModal() {
    const grid = document.getElementById('sceneTypeGrid');
    grid.innerHTML = '';
    for (const [key, desc] of Object.entries(templates.scene_types)) {
        grid.innerHTML += `
            <div class="template-card" onclick="insertScene('${key}')">
                <div class="tc-name">${key}</div>
                <div class="tc-desc">${desc}</div>
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
    toast('Scaffold loaded — fill in your content', 'success');
}

async function loadExample(domain) {
    const resp = await fetch(`/api/example/${domain}`);
    storyboard = await resp.json();
    syncUI();
    toast('Example loaded — ready to render', 'success');
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
    toast('Scaffold generated', 'success');
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
    } catch(e) { /* ignore parse errors during typing */ }
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
    } catch(e) { toast('Invalid JSON', 'error'); }
}

// ── Scene List ──
function renderSceneList() {
    const el = document.getElementById('sceneList');
    el.innerHTML = '';
    (storyboard.scenes || []).forEach((scene, i) => {
        const active = i === selectedSceneIdx ? 'active' : '';
        const label = scene.header || scene.title || scene.hook_text || scene.id || '(unnamed)';
        el.innerHTML += `
            <div class="scene-item ${active}" onclick="selectScene(${i})">
                <span class="scene-badge">${scene.type}</span>
                <span class="scene-label">${label.substring(0, 40)}</span>
                <div class="scene-actions">
                    <button class="btn btn-icon btn-sm" onclick="event.stopPropagation();moveScene(${i},-1)" title="Move up">&#x25B2;</button>
                    <button class="btn btn-icon btn-sm" onclick="event.stopPropagation();moveScene(${i},1)" title="Move down">&#x25BC;</button>
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

function insertScene(type) {
    const schema = templates.scene_schemas?.[type];
    const newScene = schema ? { ...schema.example, id: `${type}_${storyboard.scenes.length}` } : { type, id: `scene_${storyboard.scenes.length}` };
    storyboard.scenes.push(newScene);
    closeModal('addSceneModal');
    selectedSceneIdx = storyboard.scenes.length - 1;
    syncUI();
    toast(`Added ${type} scene`, 'success');
}

// ── Preview ──
function updatePreviewDropdown() {
    const sel = document.getElementById('previewScene');
    sel.innerHTML = '';
    (storyboard.scenes || []).forEach((s, i) => {
        const label = s.header || s.title || s.hook_text || s.id || `Scene ${i}`;
        sel.innerHTML += `<option value="${i}">${i}: ${label.substring(0, 25)}</option>`;
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
        toast(`Valid: "${data.title}" — ${data.scenes} scenes`, 'success');
    } else {
        toast(`Invalid: ${data.error}`, 'error');
    }
}

// ── Render ──
async function startRender() {
    try {
        storyboard = JSON.parse(document.getElementById('jsonEditor').value);
    } catch(e) {
        toast('Invalid JSON', 'error');
        return;
    }

    const btn = document.getElementById('renderBtn');
    btn.disabled = true;
    btn.textContent = 'Rendering...';
    document.getElementById('progressBar').style.display = 'block';
    document.getElementById('renderStatus').textContent = 'Starting render...';
    document.getElementById('renderStatus').className = 'render-status';

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
        status.textContent = `Rendering... (${elapsed}s)`;
        setTimeout(pollJob, 2000);
    } else if (job.status === 'done') {
        status.textContent = `Done! ${job.size_mb?.toFixed(1)} MB`;
        status.className = 'render-status done';
        btn.disabled = false;
        btn.textContent = 'Render Video';
        document.getElementById('progressBar').style.display = 'none';

        // Show download button
        const dl = document.createElement('a');
        dl.href = `/api/download/${currentJobId}`;
        dl.className = 'btn btn-primary';
        dl.style.cssText = 'display:inline-block;margin-top:8px;text-decoration:none;text-align:center;width:100%';
        dl.textContent = 'Download Video';
        status.after(dl);

        toast('Render complete!', 'success');
    } else {
        status.textContent = `Failed: ${job.error || 'Unknown error'}`;
        status.className = 'render-status error';
        btn.disabled = false;
        btn.textContent = 'Render Video';
        document.getElementById('progressBar').style.display = 'none';
        toast('Render failed', 'error');
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
    setTimeout(() => el.classList.remove('show'), 3000);
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import webbrowser
    port = 5100
    print(f"[vidgen] Starting web UI at http://localhost:{port}")
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
