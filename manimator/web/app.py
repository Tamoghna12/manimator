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
WORK_DIR = Path.cwd() / "manimator_output"
WORK_DIR.mkdir(exist_ok=True)

# Allowed values for user-controlled parameters
ALLOWED_FORMATS = {"instagram_reel", "tiktok", "youtube_short", "instagram_square",
                   "linkedin", "linkedin_square", "presentation"}
ALLOWED_VOICES = {"aria", "guy", "jenny", "davis", "andrew", "emma"}
ALLOWED_MUSIC = {"", "none", "ambient", "corporate", "cinematic"}


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

    dt = None
    if domain and domain in DOMAIN_TEMPLATES:
        dt = DOMAIN_TEMPLATES[domain]
        structure = dt.get("structure", structure)
        theme = dt.get("theme", theme)

    # Use custom_scenes from domain template if available, else fall back to structure
    if dt and "custom_scenes" in dt:
        scene_defs = dt["custom_scenes"]
    else:
        struct = STRUCTURES.get(structure, STRUCTURES["explainer"])
        scene_defs = struct["scenes"]

    scaffold_content = dt.get("scaffold_content", {}) if dt else {}
    scenes = []
    # Track how many times each type appears (for multi-instance types like bullet_list)
    type_counts = {}

    for i, s in enumerate(scene_defs):
        stype = s["type"]
        schema = SCENE_SCHEMAS.get(stype, {})
        example = schema.get("example", {})

        # Start with schema example as base
        scene = dict(example)
        scene["id"] = f"scene_{i}"

        # Apply domain-specific scaffold content
        content = scaffold_content.get(stype)
        if content is not None:
            # Handle multiple instances of same type (e.g., two bullet_lists)
            count = type_counts.get(stype, 0)
            if isinstance(content, list):
                if count < len(content):
                    scene.update(content[count])
                # else keep schema default
            else:
                if count == 0:
                    scene.update(content)
            type_counts[stype] = count + 1
        else:
            type_counts[stype] = type_counts.get(stype, 0) + 1

        # Override title/hook with user's topic
        if stype == "title":
            scene["title"] = topic
        elif stype == "hook":
            if not dt:  # Only use generic text if no domain template
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


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate a storyboard using an LLM provider.

    Accepts topic, provider, model, api_key, and optional domain/structure/format/theme.
    API key is passed per-request from the browser and never logged or persisted.
    """
    data = request.get_json(force=True, silent=True) or {}
    log.info("Generate request: provider=%s model=%s topic=%s base_url=%s",
             data.get("provider"), data.get("model"), data.get("topic", "")[:50], data.get("base_url"))

    topic = data.get("topic", "").strip()
    provider = data.get("provider", "openai")
    model = data.get("model") or None
    api_key = data.get("api_key", "").strip()
    domain = data.get("domain") or None
    structure = data.get("structure", "explainer")
    fmt = data.get("format", "presentation")
    theme = data.get("theme", "wong")
    base_url = data.get("base_url", "").strip()

    if not topic:
        return jsonify({"error": "Topic is required"}), 400
    if not api_key and provider != "ollama":
        return jsonify({"error": "API key is required"}), 400

    try:
        from manimator.llm import generate_storyboard
        result = generate_storyboard(
            topic=topic,
            provider=provider,
            model=model,
            api_key=api_key,
            domain=domain,
            structure=structure,
            format_type=fmt,
            theme=theme,
            base_url=base_url,
        )
        log.info("Generate succeeded: %d scenes", len(result.get("scenes", [])))
        return jsonify(result)
    except ValueError as e:
        log.warning("Generate ValueError: %s", e)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log.exception("LLM generation failed")
        return jsonify({"error": f"Generation failed: {str(e)[:500]}"}), 500


@app.route("/api/providers", methods=["GET"])
def api_providers():
    """Return available LLM providers and their models."""
    from manimator.llm import list_providers, PROVIDERS
    providers = {}
    for name, models in list_providers().items():
        providers[name] = {
            "models": models,
            "default": PROVIDERS[name]["default"],
        }
    return jsonify(providers)


@app.route("/api/ollama/models", methods=["GET"])
def api_ollama_models():
    """Fetch locally installed Ollama models from the Ollama API.

    Tries the requested base_url first, then falls back to host.docker.internal
    so Docker containers can reach Ollama running on the host automatically.
    """
    import urllib.request
    import urllib.error

    def _strip_v1(url: str) -> str:
        url = url.rstrip("/")
        if url.endswith("/v1"):
            url = url[:-3]
        return url

    def _fetch_models(base: str):
        with urllib.request.urlopen(f"{base}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read())
        return [m["name"] for m in data.get("models", [])]

    requested = _strip_v1(request.args.get("base_url", "http://localhost:11434"))

    # Build fallback list: if user specified localhost, also try host.docker.internal
    candidates = [requested]
    if "localhost" in requested or "127.0.0.1" in requested:
        fallback = requested.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
        candidates.append(fallback)

    last_error = None
    for base in candidates:
        try:
            models = _fetch_models(base)
            # If we succeeded via a different URL, tell the frontend to update
            return jsonify({"models": models, "resolved_url": base + "/v1"})
        except Exception as exc:
            last_error = exc
            log.debug("Ollama probe %s failed: %s", base, exc)
            continue

    log.warning("Ollama not reachable at %s: %s", requested, last_error)
    return jsonify({"models": [], "error": "Ollama not reachable at " + requested}), 200


@app.route("/api/render", methods=["POST"])
def api_render():
    """Start a render job (runs in bounded thread pool)."""
    data = request.json
    storyboard = data.get("storyboard")
    fmt = data.get("format", "instagram_reel")
    narrate = bool(data.get("narrate", False))
    voice = data.get("voice", "aria")
    music = data.get("music", "")

    if not storyboard:
        return jsonify({"error": "No storyboard provided"}), 400

    # Validate format, voice, and music against allow-lists
    if fmt not in ALLOWED_FORMATS:
        return jsonify({"error": f"Invalid format: {fmt}"}), 400
    if voice not in ALLOWED_VOICES:
        return jsonify({"error": f"Invalid voice: {voice}"}), 400
    if music not in ALLOWED_MUSIC:
        return jsonify({"error": f"Invalid music preset: {music}"}), 400

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
        import threading
        import os as _os

        try:
            is_portrait = fmt in ("instagram_reel", "tiktok", "youtube_short", "instagram_square")
            module = "manimator.portrait" if is_portrait else "manimator.orchestrator"
            cmd = [
                "python", "-u", "-m", module,   # -u = unbuffered output
                "-s", str(json_path),
                "-o", str(output_path),
            ]
            if is_portrait:
                cmd.extend(["--format", fmt, "--workers", "4"])
            else:
                cmd.extend(["-q", "low"])
            if narrate:
                cmd.extend(["--narrate", "--voice", voice])
            if music and music not in ("", "none"):
                cmd.extend(["--music", music])

            env = {**_os.environ, "PYTHONUNBUFFERED": "1"}
            log.info("Render cmd: %s", " ".join(cmd))

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(Path.cwd()),
                env=env,
            )

            # Read stdout in a background thread so it never blocks the timeout
            lines = []
            def _read():
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        lines.append(line)
                        JOBS[job_id]["log"] = "\n".join(lines[-100:])
                        log.info("Render[%s]: %s", job_id, line)

            reader = threading.Thread(target=_read, daemon=True)
            reader.start()

            try:
                proc.wait(timeout=1800)  # 30 min — large renders take 8-15 min
            except subprocess.TimeoutExpired:
                proc.kill()
                reader.join(timeout=2)
                raise

            reader.join(timeout=5)

            if proc.returncode == 0 and output_path.exists():
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["output"] = str(output_path)
                JOBS[job_id]["size_mb"] = output_path.stat().st_size / (1024 * 1024)
                log.info("Render done: job=%s size=%.1fMB", job_id, JOBS[job_id]["size_mb"])
            else:
                JOBS[job_id]["status"] = "failed"
                last_lines = "\n".join(lines[-30:])
                JOBS[job_id]["error"] = last_lines or f"Process exited with code {proc.returncode}"
                log.error("Render failed: job=%s rc=%d\n%s", job_id, proc.returncode, last_lines)
        except subprocess.TimeoutExpired:
            JOBS[job_id]["status"] = "failed"
            last_lines = "\n".join(lines[-10:]) if lines else "(no output)"
            JOBS[job_id]["error"] = f"Render timed out after 30 minutes. Last output:\n{last_lines}"
            log.error("Render timeout: job=%s last_output=%s", job_id, last_lines)
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


# ── Upload Routes ─────────────────────────────────────────────────────────────


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Upload a completed render to YouTube."""
    data = request.json
    job_id = data.get("job_id", "")
    privacy = data.get("privacy", "private")

    if not re.match(r'^[a-f0-9]{8}$', job_id):
        return jsonify({"error": "Invalid job ID"}), 400
    if privacy not in ("private", "unlisted", "public"):
        return jsonify({"error": "Invalid privacy setting"}), 400

    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "No completed render for this job"}), 404

    output = Path(job["output"])
    if not output.exists():
        return jsonify({"error": "Render file not found"}), 404

    # Load storyboard from the job's JSON file
    json_path = WORK_DIR / f"{job_id}.json"
    if not json_path.exists():
        return jsonify({"error": "Storyboard JSON not found for job"}), 404

    try:
        with open(json_path) as f:
            storyboard_data = json.load(f)

        from manimator.uploader import upload_short
        result = upload_short(
            video_path=str(output),
            storyboard_data=storyboard_data,
            privacy=privacy,
        )
        return jsonify(result)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log.exception("Upload failed: job=%s", job_id)
        return jsonify({"error": f"Upload failed: {str(e)[:300]}"}), 500


# ── Pipeline Routes ───────────────────────────────────────────────────────────

_pipeline_instance = None


def _get_pipeline():
    global _pipeline_instance
    if _pipeline_instance is None:
        from manimator.pipeline import Pipeline
        _pipeline_instance = Pipeline()
    return _pipeline_instance


@app.route("/api/pipeline/status", methods=["GET"])
def api_pipeline_status():
    """Return pipeline status counts."""
    pipe = _get_pipeline()
    return jsonify(pipe.get_status())


@app.route("/api/pipeline/videos", methods=["GET"])
def api_pipeline_videos():
    """List pipeline videos with optional status filter."""
    pipe = _get_pipeline()
    status = request.args.get("status")
    limit = min(int(request.args.get("limit", 20)), 100)
    videos = pipe.list_videos(status=status, limit=limit)
    return jsonify(videos)


@app.route("/api/pipeline/add-topics", methods=["POST"])
def api_pipeline_add_topics():
    """Add topics to the pipeline queue."""
    data = request.json
    topics = data.get("topics", [])
    if not topics:
        return jsonify({"error": "No topics provided"}), 400
    if not all(isinstance(t, dict) and "topic" in t for t in topics):
        return jsonify({"error": "Each topic must be a dict with a 'topic' key"}), 400

    pipe = _get_pipeline()
    ids = pipe.add_topics(topics)
    return jsonify({"added": len(ids), "ids": ids})


@app.route("/api/pipeline/import-csv", methods=["POST"])
def api_pipeline_import_csv():
    """Parse a CSV of topics and optionally add them to the pipeline.

    Accepts multipart/form-data with a ``file`` field, or JSON body with
    a ``csv_text`` field.

    Query param ``action``:
      - ``preview`` (default) — parse and return rows without adding
      - ``import``            — parse and add to pipeline, return IDs
    """
    from manimator.pipeline import parse_csv as _parse_csv

    # Get CSV text from file upload or JSON body
    if "file" in request.files:
        f = request.files["file"]
        csv_text = f.read().decode("utf-8", errors="replace")
    else:
        body = request.get_json(force=True, silent=True) or {}
        csv_text = body.get("csv_text", "")

    if not csv_text.strip():
        return jsonify({"error": "No CSV data provided"}), 400

    try:
        topics, warnings = _parse_csv(csv_text)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if not topics:
        return jsonify({"error": "No valid topics found in CSV", "warnings": warnings}), 400

    action = request.args.get("action", "preview")
    if action == "import":
        pipe = _get_pipeline()
        ids = pipe.add_topics(topics)
        return jsonify({
            "imported": len(ids),
            "ids": ids,
            "topics": topics,
            "warnings": warnings,
        })

    # Default: preview only
    from collections import Counter
    categories = dict(Counter(t.get("category") or "(none)" for t in topics))
    return jsonify({
        "count": len(topics),
        "topics": topics,
        "categories": categories,
        "warnings": warnings,
    })


@app.route("/api/pipeline/add-storyboards", methods=["POST"])
def api_pipeline_add_storyboards():
    """Import pre-written storyboard JSONs (no LLM needed)."""
    data = request.json
    storyboards = data.get("storyboards", [])
    if not storyboards:
        return jsonify({"error": "No storyboards provided"}), 400

    entries = []
    for i, entry in enumerate(storyboards):
        sb = entry.get("storyboard")
        if not sb or "meta" not in sb or "scenes" not in sb:
            return jsonify({"error": f"Entry {i}: must have storyboard with meta and scenes"}), 400
        try:
            Storyboard(**sb)
        except Exception as e:
            return jsonify({"error": f"Entry {i}: invalid storyboard — {e}"}), 400
        entries.append(entry)

    pipe = _get_pipeline()
    ids = pipe.add_storyboards(entries)
    return jsonify({"added": len(ids), "ids": ids})


@app.route("/api/pipeline/render", methods=["POST"])
def api_pipeline_render():
    """Render queued storyboards (no LLM needed, runs in thread pool)."""
    data = request.json or {}
    limit = min(int(data.get("limit", 5)), 20)
    upload = bool(data.get("upload", False))
    privacy = data.get("privacy", "private")
    narrate = bool(data.get("narrate", False))
    voice = data.get("voice", "aria")
    music = data.get("music", "")

    run_id = str(uuid.uuid4())[:8]

    def _run():
        pipe = _get_pipeline()
        try:
            results = pipe.run_renders(
                limit=limit, upload=upload, privacy=privacy,
                narrate=narrate, voice=voice, music=music,
            )
            log.info("Render run %s complete: %d results", run_id, len(results))
        except Exception as e:
            log.exception("Render run %s failed", run_id)

    _render_pool.submit(_run)
    return jsonify({"run_id": run_id, "status": "started", "limit": limit})


@app.route("/api/pipeline/run", methods=["POST"])
def api_pipeline_run():
    """Trigger a full pipeline run with LLM (executes in thread pool)."""
    data = request.json or {}
    provider = data.get("provider", "openai")
    model = data.get("model")
    api_key = data.get("api_key", "").strip()
    limit = min(int(data.get("limit", 5)), 20)
    upload = bool(data.get("upload", False))
    privacy = data.get("privacy", "private")
    narrate = bool(data.get("narrate", False))
    voice = data.get("voice", "aria")
    music = data.get("music", "")

    if not api_key and provider != "ollama":
        return jsonify({"error": "API key is required"}), 400

    run_id = str(uuid.uuid4())[:8]

    def _run():
        pipe = _get_pipeline()
        try:
            results = pipe.run_pipeline(
                provider=provider, model=model, api_key=api_key,
                limit=limit, upload=upload, privacy=privacy,
                narrate=narrate, voice=voice, music=music,
            )
            log.info("Pipeline run %s complete: %d results", run_id, len(results))
        except Exception as e:
            log.exception("Pipeline run %s failed", run_id)

    _render_pool.submit(_run)
    return jsonify({"run_id": run_id, "status": "started", "limit": limit})


# ── Analytics Routes ──────────────────────────────────────────────────────────

_analytics_instance = None


def _get_analytics():
    global _analytics_instance
    if _analytics_instance is None:
        from manimator.analytics import Analytics
        _analytics_instance = Analytics()
    return _analytics_instance


@app.route("/api/analytics/summary", methods=["GET"])
def api_analytics_summary():
    """Return analytics insights summary."""
    analytics = _get_analytics()
    return jsonify(analytics.get_insights())


@app.route("/api/analytics/top", methods=["GET"])
def api_analytics_top():
    """Return top-performing videos."""
    analytics = _get_analytics()
    metric = request.args.get("metric", "views")
    limit = min(int(request.args.get("limit", 10)), 50)
    days = int(request.args.get("days", 30))
    try:
        top = analytics.get_top_videos(metric=metric, limit=limit, days=days)
        return jsonify(top)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/analytics/domains", methods=["GET"])
def api_analytics_domains():
    """Return per-domain performance breakdown."""
    analytics = _get_analytics()
    days = int(request.args.get("days", 30))
    return jsonify(analytics.get_domain_performance(days=days))


@app.route("/api/analytics/sync", methods=["POST"])
def api_analytics_sync():
    """Trigger a metrics sync from YouTube Analytics."""
    data = request.json or {}
    days = int(data.get("days", 7))
    analytics = _get_analytics()
    try:
        count = analytics.sync_metrics(days=days)
        return jsonify({"synced": count})
    except Exception as e:
        log.exception("Analytics sync failed")
        return jsonify({"error": f"Sync failed: {str(e)[:300]}"}), 500


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
    /* ── Light theme inspired by OpenReel: clean whites, deep navy, coral CTAs ── */
    --bg: #f5f7fa;
    --bg-raised: #ffffff;
    --bg-card: #f0f2f7;
    --bg-card-hover: #e8ebf2;
    --bg-input: #f0f2f7;
    --border: #dfe3ec;
    --border-subtle: #e8ebf2;
    --border-focus: #4f6ef7;
    --text: #1a1f36;
    --text-secondary: #4a5578;
    --text-muted: #8892a8;
    --accent: #4f6ef7;
    --accent-hover: #6b84ff;
    --accent-dim: rgba(79,110,247,0.08);
    --accent-glow: rgba(79,110,247,0.20);
    --green: #10b981;
    --green-dim: rgba(16,185,129,0.08);
    --orange: #f97316;
    --orange-dim: rgba(249,115,22,0.08);
    --red: #ef4444;
    --red-dim: rgba(239,68,68,0.08);
    --purple: #8b5cf6;
    --purple-dim: rgba(139,92,246,0.08);
    --cyan: #06b6d4;
    --cyan-dim: rgba(6,182,212,0.08);
    --pink: #ec4899;
    --pink-dim: rgba(236,72,153,0.08);
    /* ── CTA / warm accent ── */
    --cta: #ff6b4a;
    --cta-hover: #ff8266;
    --cta-dim: rgba(255,107,74,0.10);
    --cta-glow: rgba(255,107,74,0.25);
    /* ── Deep navy for contrast elements ── */
    --navy: #1a1f36;
    --navy-light: #2d3452;
    --radius: 12px;
    --radius-sm: 8px;
    --radius-lg: 16px;
    --shadow-sm: 0 1px 3px rgba(26,31,54,0.06);
    --shadow-md: 0 4px 16px rgba(26,31,54,0.08);
    --shadow-lg: 0 8px 32px rgba(26,31,54,0.12);
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

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: #c5cad8; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #a0a8bc; }

/* ── Grid Layout ── */
.app {
    display: grid;
    grid-template-rows: 52px 1fr 120px;
    grid-template-columns: 280px 1fr 360px;
    grid-template-areas:
        "toolbar toolbar toolbar"
        "left-panel preview right-panel"
        "timeline timeline timeline";
    height: 100vh;
}

.app.left-collapsed {
    grid-template-columns: 0px 1fr 360px;
}
.app.right-collapsed {
    grid-template-columns: 280px 1fr 0px;
}
.app.left-collapsed.right-collapsed {
    grid-template-columns: 0px 1fr 0px;
}

.toolbar {
    grid-area: toolbar;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 16px;
    height: 52px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-raised);
    box-shadow: 0 1px 4px rgba(26,31,54,0.06);
    z-index: 10;
}

.left-panel {
    grid-area: left-panel;
    background: var(--bg-raised);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    transition: width var(--transition), opacity var(--transition);
}
.app.left-collapsed .left-panel { opacity: 0; pointer-events: none; overflow: hidden; }

.preview-canvas {
    grid-area: preview;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--bg);
}

.right-panel {
    grid-area: right-panel;
    background: var(--bg-raised);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    transition: width var(--transition), opacity var(--transition);
}
.app.right-collapsed .right-panel { opacity: 0; pointer-events: none; overflow: hidden; }

.timeline {
    grid-area: timeline;
    background: var(--bg-raised);
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

/* ── Toolbar Styles ── */
.toolbar-brand {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-right: 8px;
}
.toolbar-brand .logo {
    width: 28px; height: 28px;
    border-radius: 8px;
    background: linear-gradient(135deg, var(--navy), var(--cta));
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; font-weight: 800; color: white;
    box-shadow: 0 2px 8px var(--cta-glow);
    flex-shrink: 0;
}
.toolbar-brand span {
    font-size: 15px; font-weight: 800;
    background: linear-gradient(135deg, var(--navy), var(--navy-light));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.toolbar-title {
    font-size: 13px; font-weight: 600; color: var(--navy);
    max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    padding: 4px 10px; border-radius: 6px; background: var(--bg-card); border: 1px solid var(--border);
}
.toolbar-group { display: flex; gap: 6px; align-items: center; }
.toolbar-progress {
    position: absolute; bottom: 0; left: 0; right: 0; height: 3px;
    background: var(--bg-input); overflow: hidden;
}
.toolbar-progress .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--cta));
    border-radius: 2px;
    animation: indeterminate 1.8s ease-in-out infinite;
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
    padding: 10px 8px;
    font-size: 10px;
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

.tab:hover { color: var(--text-secondary); background: var(--bg-card); }
.tab.active { color: var(--cta); border-bottom-color: var(--cta); background: linear-gradient(180deg, var(--cta-dim), transparent); }

/* ── Tab Transitions ── */
.tab-content { animation: tabFadeIn 0.2s ease-out; }
@keyframes tabFadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

/* ── Left Panel Content ── */
.left-panel-content {
    flex: 1;
    overflow-y: auto;
    padding: 0;
}

/* ── Preview Canvas (Center Hero) ── */
.preview-area {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    position: relative;
    overflow: hidden;
}

.preview-controls {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-raised);
}

.preview-phone-frame {
    width: 360px;
    height: 640px;
    position: relative;
    overflow: hidden;
    border-radius: 20px;
    border: 2px solid var(--border);
    box-shadow: 0 8px 40px rgba(26,31,54,0.12), 0 0 0 1px var(--border);
    background: repeating-conic-gradient(#e8ebf2 0% 25%, #ffffff 0% 50%) 50% / 12px 12px;
    flex-shrink: 0;
}

.preview-phone-frame iframe {
    width: 1080px;
    height: 1920px;
    border: none;
    background: white;
    transform: scale(0.333);
    transform-origin: top left;
    position: absolute;
    top: 0; left: 0;
}

.preview-empty {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: var(--text-muted);
    font-size: 12px;
    text-align: center;
    padding: 24px;
}
.preview-empty-icon { font-size: 40px; opacity: 0.3; }
.preview-empty-text { line-height: 1.5; }

.preview-status {
    padding: 6px 16px;
    font-size: 11px;
    color: var(--text-muted);
    text-align: center;
    border-top: 1px solid var(--border-subtle);
    background: var(--bg-raised);
}
.preview-status.done { color: var(--green); font-weight: 600; }
.preview-status.error { color: var(--red); }

/* ── Right Panel ── */
.right-panel-header {
    display: flex;
    align-items: center;
    gap: 0;
    padding: 0;
    border-bottom: 1px solid var(--border);
    background: var(--bg-raised);
}

.right-panel-tab {
    flex: 1;
    padding: 10px 8px;
    font-size: 10px;
    font-weight: 600;
    color: var(--text-muted);
    cursor: pointer;
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    border-bottom: 2px solid transparent;
    transition: var(--transition);
    user-select: none;
}
.right-panel-tab:hover { color: var(--text-secondary); background: var(--bg-card); }
.right-panel-tab.active { color: var(--cta); border-bottom-color: var(--cta); background: var(--cta-dim); }

.right-panel-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.scene-editor-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

#sceneEditor {
    flex: 1;
    width: 100%;
    padding: 12px;
    background: #fafbfd;
    color: var(--navy);
    border: none;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    line-height: 1.7;
    resize: none;
    outline: none;
    tab-size: 2;
}

.scene-editor-actions {
    padding: 8px 12px;
    display: flex;
    gap: 6px;
    border-top: 1px solid var(--border-subtle);
    background: var(--bg-raised);
}

#jsonEditor {
    flex: 1;
    width: 100%;
    padding: 12px;
    background: #fafbfd;
    color: var(--navy);
    border: none;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    line-height: 1.7;
    resize: none;
    outline: none;
    tab-size: 2;
}

/* ── Timeline ── */
.timeline-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-bottom: 1px solid var(--border-subtle);
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    flex-shrink: 0;
}

.timeline-strip {
    flex: 1;
    display: flex;
    gap: 8px;
    padding: 8px 12px;
    overflow-x: auto;
    overflow-y: hidden;
    align-items: stretch;
    scroll-behavior: smooth;
}

.timeline-card {
    flex: 0 0 110px;
    padding: 10px;
    border-radius: var(--radius-sm);
    background: var(--bg-card);
    border: 2px solid var(--border);
    cursor: pointer;
    transition: var(--transition);
    display: flex;
    flex-direction: column;
    gap: 4px;
    position: relative;
    user-select: none;
}
.timeline-card:hover {
    border-color: var(--accent);
    background: var(--bg-raised);
    box-shadow: var(--shadow-sm);
}
.timeline-card.active {
    border-color: var(--cta);
    background: var(--cta-dim);
    box-shadow: 0 2px 12px var(--cta-glow);
}
.timeline-card.dragging { opacity: 0.4; }
.timeline-card.drag-over { border-left: 3px solid var(--accent); }

.timeline-card .tc-num {
    font-size: 9px; font-weight: 700; color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
}
.timeline-card.active .tc-num { color: var(--cta); }

.timeline-card .tc-type {
    font-size: 9px; font-weight: 700;
    padding: 1px 6px; border-radius: 3px;
    background: var(--bg-input); color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase; letter-spacing: 0.3px;
    align-self: flex-start;
}

.timeline-card .tc-label {
    font-size: 10px; color: var(--text-secondary);
    overflow: hidden; text-overflow: ellipsis;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    line-height: 1.3; flex: 1;
}

.timeline-card .tc-delete {
    position: absolute; top: 4px; right: 4px;
    width: 18px; height: 18px;
    border-radius: 4px; border: none;
    background: var(--red-dim); color: var(--red);
    font-size: 10px; cursor: pointer;
    display: none; align-items: center; justify-content: center;
    transition: var(--transition);
}
.timeline-card:hover .tc-delete { display: flex; }
.timeline-card .tc-delete:hover { background: var(--red); color: white; }

.timeline-add {
    flex: 0 0 60px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-sm);
    border: 2px dashed var(--border);
    cursor: pointer;
    transition: var(--transition);
    color: var(--text-muted);
    font-size: 20px;
    font-weight: 300;
}
.timeline-add:hover { border-color: var(--cta); color: var(--cta); background: var(--cta-dim); }

.panel-section {
    padding: 14px 16px 6px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    gap: 8px;
}

.panel-section::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border-subtle);
}

/* ── Template Cards ── */
.template-grid {
    padding: 4px 10px;
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
    background: var(--bg-raised);
    border-color: var(--border);
    box-shadow: var(--shadow-sm);
}
.template-card.active {
    background: var(--cta-dim);
    border-color: var(--cta);
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
.domain-bio .tc-icon { background: rgba(16,185,129,0.12); color: #059669; }
.domain-bio .tc-tag { background: rgba(16,185,129,0.12); color: #059669; }
.domain-cs .tc-icon { background: rgba(79,110,247,0.10); color: #4338ca; }
.domain-cs .tc-tag { background: rgba(79,110,247,0.10); color: #4338ca; }
.domain-math .tc-icon { background: rgba(249,115,22,0.10); color: #c2410c; }
.domain-math .tc-tag { background: rgba(249,115,22,0.10); color: #c2410c; }
.domain-gen .tc-icon { background: rgba(139,92,246,0.10); color: #7c3aed; }
.domain-gen .tc-tag { background: rgba(139,92,246,0.10); color: #7c3aed; }

/* ── Quick Start ── */
.quick-start {
    padding: 12px 10px 8px;
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
    padding: 4px 10px 12px;
    overflow-x: auto;
    scroll-snap-type: x mandatory;
}

.structure-card {
    flex: 0 0 160px;
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
    background: var(--bg-raised);
    box-shadow: var(--shadow-sm);
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
    padding: 4px 10px 12px;
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 6px;
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
    background: var(--bg-raised);
    box-shadow: var(--shadow-sm);
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

/* ── Scene Empty State ── */
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
    background: linear-gradient(135deg, var(--cta), #ff8855);
    border-color: var(--cta);
    color: white;
    box-shadow: 0 2px 12px var(--cta-glow);
}

.btn-primary:hover { background: linear-gradient(135deg, var(--cta-hover), #ffa077); box-shadow: 0 4px 16px var(--cta-glow); }

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
.btn-ghost:hover { color: var(--text); background: var(--bg-card); }

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
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-dim);
}

textarea {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    resize: vertical;
    line-height: 1.6;
}

/* (JSON editor and preview styles moved to grid sections above) */

/* ── Progress Animation ── */
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
    background: rgba(26,31,54,0.40);
    backdrop-filter: blur(8px);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 100;
}

.modal-overlay.show { display: flex; }

.modal {
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 28px;
    width: 90%;
    max-width: 760px;
    max-height: 85vh;
    overflow-y: auto;
    box-shadow: 0 24px 64px rgba(26,31,54,0.18);
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
    padding: 0 10px 12px;
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
    background: var(--navy);
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
    background: rgba(79,110,247,0.08);
    color: #4338ca;
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
    padding: 14px;
    margin: 6px 10px;
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
    background: var(--bg-raised);
    box-shadow: var(--shadow-sm);
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
.toast.success { border-color: var(--green); color: #059669; background: var(--bg-raised); }
.toast.error { border-color: var(--red); color: var(--red); background: var(--bg-raised); }

/* ── Toolbar Separator ── */
.toolbar-sep {
    width: 1px;
    height: 20px;
    background: var(--border);
}
</style>
</head>
<body>
<div class="app" id="appRoot">

    <!-- ══════════ Toolbar ══════════ -->
    <div class="toolbar" style="position:relative">
        <div class="toolbar-brand">
            <div class="logo">M</div>
            <span>manimator</span>
        </div>
        <div class="toolbar-title" id="toolbarTitle">Untitled</div>
        <span style="flex:1"></span>
        <div class="toolbar-group">
            <button class="btn btn-sm" onclick="togglePanel('left')" id="btnToggleLeft" title="Toggle tools panel">Tools</button>
            <button class="btn btn-sm" onclick="togglePanel('right')" id="btnToggleRight" title="Toggle editor panel">Editor</button>
            <div class="toolbar-sep"></div>
            <button class="btn btn-sm" onclick="openPipelineModal()">Pipeline</button>
            <button class="btn btn-sm" onclick="openAnalyticsModal()">Analytics</button>
            <div class="toolbar-sep"></div>
            <button class="btn btn-sm" onclick="validateStoryboard()">Validate</button>
            <button class="btn btn-sm" onclick="downloadJson()">Export</button>
            <button class="btn btn-sm" onclick="importJson()">Import</button>
            <div class="toolbar-sep"></div>
            <label class="toggle-label" style="font-size:11px">
                <input type="checkbox" class="toggle" id="cbNarrate" checked>
                <span>Narrate</span>
            </label>
            <button class="btn btn-sm btn-primary" onclick="startRender()" id="renderBtn">Render</button>
        </div>
        <div class="toolbar-progress" id="progressBar" style="display:none">
            <div class="progress-fill"></div>
        </div>
    </div>

    <!-- ══════════ Left Panel ══════════ -->
    <div class="left-panel" id="leftPanel">
        <div class="tab-bar">
            <div class="tab active" onclick="switchTab(this,'guide')">Guide</div>
            <div class="tab" onclick="switchTab(this,'templates')">Templates</div>
            <div class="tab" onclick="switchTab(this,'settings')">Settings</div>
        </div>

        <!-- ════ Templates Tab ════ -->
        <div class="left-panel-content tab-content" id="tab-templates" style="display:none">

            <!-- Quick Start -->
            <div class="quick-start">
                <div class="quick-start-inner">
                    <div class="form-group" style="margin-bottom:10px">
                        <label class="form-label">Topic</label>
                        <input type="text" id="topicInput" placeholder="e.g., How CRISPR-Cas9 edits genes" />
                    </div>
                    <div style="display:flex;gap:6px">
                        <button class="btn btn-primary btn-sm" onclick="scaffoldFromTopic()" style="flex:1">Scaffold</button>
                        <button class="btn btn-sm" onclick="showPromptModal()" title="LLM prompt">Prompt</button>
                    </div>
                    <div style="margin-top:6px">
                        <button class="btn btn-primary btn-sm" onclick="generateWithAI()" style="width:100%;background:linear-gradient(135deg, var(--accent), var(--purple));border-color:var(--accent)" title="Generate with AI">AI Generate</button>
                    </div>
                </div>
            </div>

            <!-- Video Structures -->
            <div class="panel-section">Video Structures</div>
            <div class="structure-scroll" id="structureList"></div>

            <!-- Domain Templates — Biology -->
            <div class="panel-section">Biology</div>
            <div class="template-grid" id="domainBioList"></div>

            <!-- Domain Templates — Computer Science -->
            <div class="panel-section">Computer Science</div>
            <div class="template-grid" id="domainCsList"></div>

            <!-- Domain Templates — Mathematics -->
            <div class="panel-section">Mathematics</div>
            <div class="template-grid" id="domainMathList"></div>

            <!-- Domain Templates — Science -->
            <div class="panel-section">Physics & Chemistry</div>
            <div class="template-grid" id="domainSciList"></div>

            <!-- Domain Templates — General -->
            <div class="panel-section">Economics & General</div>
            <div class="template-grid" id="domainGenList"></div>

            <!-- Ready-to-Render Examples -->
            <div class="panel-section">Ready-to-Render Examples</div>
            <div class="example-cards" id="exampleList"></div>

        </div>

        <!-- ════ Settings Tab ════ -->
        <div class="left-panel-content tab-content" id="tab-settings" style="display:none">
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
            <div class="settings-section">
                <h4>Background Music</h4>
                <div class="form-group">
                    <label class="form-label">Music Preset</label>
                    <select id="metaMusic">
                        <option value="none">None</option>
                        <option value="ambient">Ambient (soft, science explainers)</option>
                        <option value="corporate">Corporate (upbeat, product demos)</option>
                        <option value="cinematic">Cinematic (dramatic, high-impact)</option>
                    </select>
                </div>
            </div>
            <div class="settings-section">
                <h4>Branding &amp; CTA</h4>
                <div class="form-group">
                    <label class="form-label">Channel Name</label>
                    <input type="text" id="brandChannel" placeholder="@YourChannel" onchange="updateMeta()" />
                </div>
                <div class="form-group">
                    <label class="form-label">CTA Text</label>
                    <input type="text" id="brandCta" placeholder="Follow for more science!" onchange="updateMeta()" />
                </div>
                <div class="form-group">
                    <label class="form-label">Hook Label</label>
                    <input type="text" id="brandAccent" placeholder="Watch This" onchange="updateMeta()" />
                </div>
                <div class="form-group">
                    <label class="form-label">Social Handles (comma-separated)</label>
                    <input type="text" id="brandSocials" placeholder="@handle1, @handle2" onchange="updateMeta()" />
                </div>
                <div class="form-group">
                    <label class="form-label">Watermark Text</label>
                    <input type="text" id="brandWatermark" placeholder="Optional corner watermark" onchange="updateMeta()" />
                </div>
            </div>
            <div class="settings-section">
                <h4>AI Generation</h4>
                <div class="form-group">
                    <label class="form-label">Provider</label>
                    <select id="aiProvider" onchange="onProviderChange()">
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Anthropic</option>
                        <option value="google">Google Gemini</option>
                        <option value="zhipuai">ZhipuAI (GLM-5)</option>
                        <option value="ollama">Ollama (Local)</option>
                        <option value="openai_compatible">OpenAI-Compatible</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Model</label>
                    <select id="aiModel"></select>
                </div>
                <div class="form-group">
                    <label class="form-label">API Key</label>
                    <input type="password" id="aiApiKey" placeholder="sk-..." onchange="saveApiKey()" />
                    <span style="font-size:10px;color:var(--text-muted);margin-top:4px;display:block">Stored in browser localStorage only. Never sent to our server.</span>
                </div>
                <div class="form-group" id="aiBaseUrlGroup" style="display:none">
                    <label class="form-label">Base URL</label>
                    <div style="display:flex;gap:6px">
                        <input type="text" id="aiBaseUrl" placeholder="http://localhost:11434/v1" style="flex:1" />
                        <button onclick="populateOllamaModels(true)" title="Detect installed models" style="padding:0 10px;font-size:13px;cursor:pointer">↺</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- ════ Guide Tab ════ -->
        <div class="left-panel-content tab-content" id="tab-guide">
            <div class="guide-content">
                <div class="guide-section" style="margin-top:12px">
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
                        <p><strong>Domain Templates</strong> give you a scaffold matching your field.</p>
                        <p><strong>Ready-to-Render Examples</strong> are complete storyboards you can render immediately.</p>
                        <p><strong>Video Structures</strong> define scene sequence without domain-specific content.</p>
                        <div class="tip">
                            <span class="tip-icon">*</span>
                            <p>Enter a topic in Quick Start before clicking a template.</p>
                        </div>
                    </div>
                </div>

                <div class="guide-section">
                    <h3><span class="step-num">2</span> Edit Your Storyboard</h3>
                    <div class="guide-card">
                        <p><code>"meta"</code> — title, color theme, format, resolution</p>
                        <p><code>"scenes"</code> — array of scene objects with a <code>"type"</code> field</p>
                        <p>Edit JSON in the right panel. Use the timeline to reorder scenes.</p>
                    </div>
                </div>

                <div class="guide-section">
                    <h3><span class="step-num">3</span> Scene Types</h3>
                    <div class="guide-card">
                        <div class="scene-ref-grid">
                            <div class="scene-ref-item"><span class="sri-name">hook</span><span class="sri-desc">Bold opener</span></div>
                            <div class="scene-ref-item"><span class="sri-name">title</span><span class="sri-desc">Title card</span></div>
                            <div class="scene-ref-item"><span class="sri-name">bullet_list</span><span class="sri-desc">Key points</span></div>
                            <div class="scene-ref-item"><span class="sri-name">flowchart</span><span class="sri-desc">Process flow</span></div>
                            <div class="scene-ref-item"><span class="sri-name">bar_chart</span><span class="sri-desc">Data bars</span></div>
                            <div class="scene-ref-item"><span class="sri-name">scatter_plot</span><span class="sri-desc">XY clusters</span></div>
                            <div class="scene-ref-item"><span class="sri-name">comparison_table</span><span class="sri-desc">Side-by-side</span></div>
                            <div class="scene-ref-item"><span class="sri-name">two_panel</span><span class="sri-desc">Split view</span></div>
                            <div class="scene-ref-item"><span class="sri-name">equation</span><span class="sri-desc">Math formula</span></div>
                            <div class="scene-ref-item"><span class="sri-name">pipeline_diagram</span><span class="sri-desc">System arch</span></div>
                            <div class="scene-ref-item"><span class="sri-name">closing</span><span class="sri-desc">References</span></div>
                        </div>
                    </div>
                </div>

                <div class="guide-section">
                    <h3><span class="step-num">4</span> Preview &amp; Render</h3>
                    <div class="guide-card">
                        <p>The center preview shows each scene live. Click scenes in the timeline below to switch.</p>
                        <p>Click <strong>Render</strong> in the toolbar to generate the final video.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ══════════ Preview Canvas (Center) ══════════ -->
    <div class="preview-canvas">
        <div class="preview-controls">
            <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted)">Preview</span>
            <select id="previewScene" onchange="previewCurrentScene()" style="width:180px;padding:4px 8px;font-size:11px;margin-left:auto"></select>
            <span style="font-size:10px;color:var(--text-muted)" id="renderEngineHint">Engine: HTML/CSS</span>
        </div>
        <div class="preview-area">
            <div class="preview-phone-frame">
                <div class="preview-empty" id="previewEmpty">
                    <div class="preview-empty-icon">&#9654;</div>
                    <div class="preview-empty-text">Pick a template or add scenes<br>to see a live preview</div>
                </div>
                <iframe id="previewIframe" sandbox="allow-scripts" style="display:none"></iframe>
            </div>
        </div>
        <div class="preview-status" id="renderStatus"></div>
    </div>

    <!-- ══════════ Right Panel (JSON Editor) ══════════ -->
    <div class="right-panel" id="rightPanel">
        <div class="right-panel-header">
            <div class="right-panel-tab active" onclick="switchRightView(this,'scene')" id="rpTabScene">Scene</div>
            <div class="right-panel-tab" onclick="switchRightView(this,'full')" id="rpTabFull">Full JSON</div>
            <button class="btn btn-sm btn-ghost" onclick="formatJson()" style="margin:0 6px;padding:4px 10px" title="Format JSON">Fmt</button>
        </div>
        <div class="right-panel-body">
            <!-- Scene Editor View -->
            <div class="scene-editor-area" id="sceneEditorView">
                <textarea id="sceneEditor" spellcheck="false" placeholder="Select a scene in the timeline to edit its JSON here..."></textarea>
                <div class="scene-editor-actions">
                    <button class="btn btn-sm btn-primary" onclick="applySceneEdit()" style="flex:1">Apply</button>
                    <button class="btn btn-sm" onclick="resetSceneEdit()">Reset</button>
                </div>
            </div>
            <!-- Full JSON View -->
            <div class="scene-editor-area" id="fullJsonView" style="display:none">
                <textarea id="jsonEditor" spellcheck="false"></textarea>
            </div>
        </div>
    </div>

    <!-- ══════════ Timeline (Bottom) ══════════ -->
    <div class="timeline">
        <div class="timeline-header">
            <span>Timeline</span>
            <span style="flex:1"></span>
            <button class="btn btn-sm btn-ghost" onclick="duplicateScene()" title="Duplicate selected scene" style="padding:2px 8px;font-size:10px">Dup</button>
            <span style="font-size:10px;color:var(--text-muted)" id="sceneCount">0 scenes</span>
        </div>
        <div class="timeline-strip" id="timelineStrip">
            <div class="timeline-add" onclick="addScene()" title="Add scene">+</div>
        </div>
    </div>
</div>

<!-- ══════════ Pipeline Modal ══════════ -->
<div class="modal-overlay" id="pipelineModal">
    <div class="modal" style="max-width:900px">
        <h2>Pipeline</h2>
        <p class="modal-subtitle">Bulk import, queue management, and rendered videos.</p>

        <!-- Bulk CSV Import -->
        <details id="csvImportSection" style="margin-bottom:16px;border:1px solid var(--border);border-radius:8px">
            <summary style="padding:10px 14px;font-size:13px;font-weight:600;cursor:pointer;user-select:none">
                Bulk Import from CSV
            </summary>
            <div style="padding:14px;border-top:1px solid var(--border)">
                <p style="font-size:12px;color:var(--text-muted);margin-bottom:10px">
                    CSV columns: <code>topic</code> (required), <code>category</code>, <code>domain</code>,
                    <code>structure</code>, <code>format</code>, <code>theme</code>, <code>voice</code>, <code>priority</code>
                </p>
                <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px">
                    <input type="file" id="csvFileInput" accept=".csv,.txt"
                           style="font-size:12px;flex:1" onchange="csvFileSelected()">
                    <button class="btn btn-sm" onclick="downloadCsvTemplate()">Template</button>
                </div>
                <div id="csvPreviewArea" style="display:none">
                    <div id="csvSummary" style="font-size:12px;margin-bottom:8px"></div>
                    <div style="overflow-x:auto;max-height:200px;overflow-y:auto">
                        <table id="csvPreviewTable" style="width:100%;font-size:11px;border-collapse:collapse">
                            <thead id="csvPreviewHead" style="position:sticky;top:0;background:var(--bg-raised)"></thead>
                            <tbody id="csvPreviewBody"></tbody>
                        </table>
                    </div>
                    <div id="csvWarnings" style="font-size:11px;color:#e07c00;margin-top:6px"></div>
                    <div style="display:flex;gap:8px;margin-top:10px">
                        <button class="btn btn-sm btn-primary" onclick="importCsv()" id="csvImportBtn">
                            Add to Queue
                        </button>
                        <span id="csvImportStatus" style="font-size:12px;align-self:center"></span>
                    </div>
                </div>
            </div>
        </details>

        <h3 style="margin-bottom:12px;font-size:14px">Pipeline Status</h3>
        <div id="pipelineStatus" style="margin-bottom:12px;font-size:13px"><em>Loading...</em></div>
        <h3 style="margin-bottom:8px;font-size:14px">Videos</h3>
        <div id="pipelineVideos" style="font-size:13px"><em>Loading...</em></div>

        <div style="margin-top:16px;text-align:right">
            <button class="btn" onclick="closeModal('pipelineModal')">Close</button>
        </div>
    </div>
</div>

<!-- ══════════ Analytics Modal ══════════ -->
<div class="modal-overlay" id="analyticsModal">
    <div class="modal" style="max-width:900px">
        <h2>Analytics</h2>
        <p class="modal-subtitle">Real performance data from YouTube Analytics API. Sync to pull latest metrics.</p>
        <div id="analyticsSummary"><em>Loading...</em></div>
        <div style="margin-top:16px;text-align:right">
            <button class="btn" onclick="closeModal('analyticsModal')">Close</button>
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
    sci: ['physics_reel', 'chemistry_reel'],
    gen: ['economics_reel', 'paper_review'],
};

const DOMAIN_ICONS = {
    biology_mechanism: 'B', biology_reel: 'B',
    cs_algorithm: 'C', cs_reel: 'C',
    math_concept: 'M', math_reel: 'M',
    physics_reel: 'P', chemistry_reel: 'C',
    economics_reel: 'E', paper_review: 'R',
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

// ── Panel Toggles ──
function togglePanel(side) {
    const app = document.getElementById('appRoot');
    if (side === 'left') {
        app.classList.toggle('left-collapsed');
    } else if (side === 'right') {
        app.classList.toggle('right-collapsed');
    }
}

// ── Right Panel View Toggle ──
function switchRightView(el, view) {
    document.querySelectorAll('.right-panel-tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    document.getElementById('sceneEditorView').style.display = view === 'scene' ? '' : 'none';
    document.getElementById('fullJsonView').style.display = view === 'full' ? '' : 'none';
}

// ── Scene Editor ──
function loadSceneEditor() {
    const editor = document.getElementById('sceneEditor');
    if (selectedSceneIdx < 0 || !storyboard.scenes?.[selectedSceneIdx]) {
        editor.value = '';
        editor.placeholder = 'Select a scene in the timeline to edit its JSON here...';
        return;
    }
    editor.value = JSON.stringify(storyboard.scenes[selectedSceneIdx], null, 2);
}

function applySceneEdit() {
    if (selectedSceneIdx < 0) { toast('No scene selected', 'error'); return; }
    try {
        const edited = JSON.parse(document.getElementById('sceneEditor').value);
        storyboard.scenes[selectedSceneIdx] = edited;
        syncUI();
        toast('Scene updated', 'success');
    } catch(e) { toast('Invalid JSON in scene editor', 'error'); }
}

function resetSceneEdit() {
    loadSceneEditor();
}

// ── Pipeline / Analytics Modals ──
function openPipelineModal() {
    document.getElementById('pipelineModal').classList.add('show');
    loadPipelineStatus();
    loadPipelineVideos();
}

function openAnalyticsModal() {
    document.getElementById('analyticsModal').classList.add('show');
    loadAnalyticsSummary();
}

// ── Timeline Renderer ──
function renderTimeline() {
    const strip = document.getElementById('timelineStrip');
    const scenes = storyboard.scenes || [];
    const countEl = document.getElementById('sceneCount');
    if (countEl) countEl.textContent = `${scenes.length} scene${scenes.length !== 1 ? 's' : ''}`;

    let html = '';
    scenes.forEach((scene, i) => {
        const active = i === selectedSceneIdx ? 'active' : '';
        const label = scene.header || scene.title || scene.hook_text || scene.id || '(unnamed)';
        html += `
            <div class="timeline-card ${active}" onclick="selectScene(${i})"
                 draggable="true"
                 ondragstart="onTimelineDragStart(event,${i})"
                 ondragover="onTimelineDragOver(event)"
                 ondragenter="onTimelineDragEnter(event)"
                 ondragleave="onTimelineDragLeave(event)"
                 ondrop="onTimelineDrop(event,${i})"
                 ondragend="onTimelineDragEnd(event)">
                <button class="tc-delete" onclick="event.stopPropagation();deleteScene(${i})" title="Delete">&#x2715;</button>
                <span class="tc-num">${i+1}</span>
                <span class="tc-type">${scene.type || '?'}</span>
                <span class="tc-label">${label.substring(0, 40)}</span>
            </div>`;
    });
    html += '<div class="timeline-add" onclick="addScene()" title="Add scene">+</div>';
    strip.innerHTML = html;
}

// ── Timeline Drag & Drop ──
let _dragTimelineIdx = null;
function onTimelineDragStart(e, idx) { _dragTimelineIdx = idx; e.currentTarget.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; }
function onTimelineDragOver(e) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }
function onTimelineDragEnter(e) { e.preventDefault(); e.currentTarget.classList.add('drag-over'); }
function onTimelineDragLeave(e) { e.currentTarget.classList.remove('drag-over'); }
function onTimelineDrop(e, targetIdx) {
    e.preventDefault(); e.currentTarget.classList.remove('drag-over');
    if (_dragTimelineIdx === null || _dragTimelineIdx === targetIdx) return;
    const scenes = storyboard.scenes;
    const [moved] = scenes.splice(_dragTimelineIdx, 1);
    scenes.splice(targetIdx, 0, moved);
    if (selectedSceneIdx === _dragTimelineIdx) selectedSceneIdx = targetIdx;
    else if (_dragTimelineIdx < selectedSceneIdx && targetIdx >= selectedSceneIdx) selectedSceneIdx--;
    else if (_dragTimelineIdx > selectedSceneIdx && targetIdx <= selectedSceneIdx) selectedSceneIdx++;
    _dragTimelineIdx = null;
    syncUI();
}
function onTimelineDragEnd(e) { e.currentTarget.classList.remove('dragging'); _dragTimelineIdx = null; }

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
    // Branding
    const br = storyboard.meta?.branding || {};
    document.getElementById('brandChannel').value = br.channel_name || '';
    document.getElementById('brandCta').value = br.cta_text || '';
    document.getElementById('brandAccent').value = br.accent_label || '';
    document.getElementById('brandSocials').value = (br.social_handles || []).join(', ');
    document.getElementById('brandWatermark').value = br.watermark_text || '';
    renderTimeline();
    loadSceneEditor();
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
        renderTimeline();
        loadSceneEditor();
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

// ── Scene Selection ──
function selectScene(idx) {
    selectedSceneIdx = idx;
    renderTimeline();
    loadSceneEditor();
    document.getElementById('previewScene').value = idx;
    previewCurrentScene();
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
    // Scroll timeline to the new scene
    const strip = document.getElementById('timelineStrip');
    if (strip) setTimeout(() => strip.scrollLeft = strip.scrollWidth, 50);
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
        const empty = document.getElementById('previewEmpty');
        iframe.srcdoc = data.html;
        iframe.style.display = 'block';
        if (empty) empty.style.display = 'none';
    }
}

// ── Meta Settings ──
function updateMeta() {
    storyboard.meta.title = document.getElementById('metaTitle').value;
    storyboard.meta.color_theme = document.getElementById('metaTheme').value;
    storyboard.meta.format = document.getElementById('metaFormat').value;

    // Branding
    const ch = document.getElementById('brandChannel').value.trim();
    const cta = document.getElementById('brandCta').value.trim();
    const accent = document.getElementById('brandAccent').value.trim();
    const socials = document.getElementById('brandSocials').value.trim();
    const wm = document.getElementById('brandWatermark').value.trim();
    if (ch || cta || accent || socials || wm) {
        storyboard.meta.branding = {
            channel_name: ch,
            cta_text: cta,
            accent_label: accent,
            social_handles: socials ? socials.split(',').map(s => s.trim()).filter(Boolean) : [],
            watermark_text: wm,
        };
    } else {
        delete storyboard.meta.branding;
    }

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
    document.getElementById('progressBar').style.display = '';
    document.getElementById('renderStatus').textContent = 'Starting render...';
    document.getElementById('renderStatus').className = 'preview-status';

    // Remove any existing download button
    const existingDl = document.querySelector('.preview-status + .btn-dl');
    if (existingDl) existingDl.remove();

    const resp = await fetch('/api/render', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            storyboard,
            format: storyboard.meta?.format || 'instagram_reel',
            narrate: document.getElementById('cbNarrate').checked,
            voice: document.getElementById('metaVoice').value,
            music: document.getElementById('metaMusic').value,
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
        status.className = 'preview-status done';
        btn.disabled = false;
        btn.textContent = 'Render';
        document.getElementById('progressBar').style.display = 'none';

        // Remove old buttons
        document.querySelectorAll('.btn-dl, .btn-upload').forEach(e => e.remove());

        const dl = document.createElement('a');
        dl.href = `/api/download/${currentJobId}`;
        dl.className = 'btn btn-primary btn-sm btn-dl';
        dl.style.cssText = 'display:inline-block;margin:4px 8px;text-decoration:none;text-align:center';
        dl.textContent = 'Download';
        status.after(dl);

        const ul = document.createElement('button');
        ul.className = 'btn btn-sm btn-upload';
        ul.style.cssText = 'display:inline-block;margin:4px 0;background:var(--purple-dim);color:var(--purple);border:1px solid var(--purple)';
        ul.textContent = 'Upload';
        ul.onclick = () => uploadToYouTube(currentJobId);
        dl.after(ul);

        toast('Render complete!', 'success');
    } else {
        status.textContent = `Failed: ${job.error || 'Unknown error'}`;
        status.className = 'preview-status error';
        btn.disabled = false;
        btn.textContent = 'Render';
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
    // Only affect tabs within the same tab-bar
    const tabBar = el.closest('.tab-bar');
    if (tabBar) tabBar.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    // Hide all left panel tab contents
    document.querySelectorAll('.left-panel-content.tab-content').forEach(c => c.style.display = 'none');
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

// ── AI Generation ──
let aiProviders = {};

async function loadAIProviders() {
    try {
        const resp = await fetch('/api/providers');
        aiProviders = await resp.json();
        onProviderChange();
        restoreApiKey();
    } catch(e) {
        // AI providers not available — SDK not installed
        console.log('AI providers not loaded:', e);
    }
}

function onProviderChange() {
    const provider = document.getElementById('aiProvider').value;
    const modelSelect = document.getElementById('aiModel');
    const baseUrlGroup = document.getElementById('aiBaseUrlGroup');
    const baseUrlInput = document.getElementById('aiBaseUrl');
    const apiKeyGroup = document.getElementById('aiApiKey').closest('.form-group');

    // Show/hide base URL field and auto-fill for Ollama
    if (provider === 'ollama') {
        baseUrlGroup.style.display = '';
        if (!baseUrlInput.value) baseUrlInput.value = 'http://localhost:11434/v1';
        apiKeyGroup.style.display = 'none';
        populateOllamaModels(false);
    } else if (provider === 'openai_compatible') {
        baseUrlGroup.style.display = '';
        apiKeyGroup.style.display = '';
        modelSelect.innerHTML = '<option value="">(enter model name)</option>';
    } else {
        baseUrlGroup.style.display = 'none';
        apiKeyGroup.style.display = '';
        modelSelect.innerHTML = '';
        const info = aiProviders[provider];
        if (info && info.models.length > 0) {
            for (const m of info.models) {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                if (m === info.default) opt.selected = true;
                modelSelect.appendChild(opt);
            }
        }
    }

    // Restore saved API key for this provider
    restoreApiKey();
}

async function populateOllamaModels(showErrors) {
    const modelSelect = document.getElementById('aiModel');
    const baseUrlInput = document.getElementById('aiBaseUrl');
    const baseUrl = baseUrlInput.value || 'http://localhost:11434/v1';

    modelSelect.innerHTML = '<option value="" disabled>Detecting models...</option>';

    try {
        const resp = await fetch(`/api/ollama/models?base_url=${encodeURIComponent(baseUrl)}`);
        const data = await resp.json();

        modelSelect.innerHTML = '';
        if (data.models && data.models.length > 0) {
            // If backend resolved via host.docker.internal, update the URL input
            if (data.resolved_url && data.resolved_url !== baseUrl) {
                baseUrlInput.value = data.resolved_url;
            }
            for (const m of data.models) {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                modelSelect.appendChild(opt);
            }
        } else {
            modelSelect.innerHTML = '<option value="">(no models found — run: ollama pull llama3.2)</option>';
            if (data.error && showErrors) toast('Ollama: ' + data.error, 'error');
        }
    } catch (e) {
        modelSelect.innerHTML = '<option value="">(could not reach Ollama)</option>';
        if (showErrors) toast('Ollama: could not connect', 'error');
    }
}

function saveApiKey() {
    const provider = document.getElementById('aiProvider').value;
    const key = document.getElementById('aiApiKey').value;
    if (key) {
        localStorage.setItem(`manimator_apikey_${provider}`, key);
    }
}

function restoreApiKey() {
    const provider = document.getElementById('aiProvider').value;
    const saved = localStorage.getItem(`manimator_apikey_${provider}`) || '';
    document.getElementById('aiApiKey').value = saved;
}

async function generateWithAI() {
    const topic = document.getElementById('topicInput').value;
    if (!topic) { toast('Enter a topic first', 'error'); return; }

    const provider = document.getElementById('aiProvider').value;
    const model = document.getElementById('aiModel').value;
    const apiKey = document.getElementById('aiApiKey').value;
    const baseUrl = document.getElementById('aiBaseUrl')?.value || '';
    const fmt = document.getElementById('metaFormat').value;
    const theme = document.getElementById('metaTheme').value;

    if (!apiKey && provider !== 'ollama') {
        toast('Set your API key in Settings → AI Generation', 'error');
        switchTab(document.querySelectorAll('.tab-bar .tab')[2], 'settings');
        return;
    }

    // Disable button and show progress
    const btns = document.querySelectorAll('[onclick="generateWithAI()"]');
    btns.forEach(b => { b.disabled = true; b.textContent = 'Generating...'; });
    toast('Generating storyboard with AI... this may take 10-30s', 'success');

    try {
        const resp = await fetch('/api/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                topic,
                provider,
                model,
                api_key: apiKey,
                format: fmt,
                theme,
                base_url: baseUrl,
            })
        });
        const data = await resp.json();

        if (resp.ok && data.scenes) {
            storyboard = data;
            syncUI();
            toast('Storyboard generated! ' + data.scenes.length + ' scenes ready.', 'success');
        } else if (resp.ok && !data.scenes) {
            console.error('Generate returned 200 but no scenes:', data);
            toast(`AI returned unexpected response — check browser console`, 'error');
        } else {
            console.error('Generate failed:', data);
            toast(`AI generation failed: ${data.error || JSON.stringify(data)}`, 'error');
        }
    } catch(e) {
        console.error('Generate exception:', e);
        toast(`AI generation error: ${e.message}`, 'error');
    } finally {
        btns.forEach(b => { b.disabled = false; b.textContent = 'Generate with AI'; });
    }
}

// Load AI providers on init
document.addEventListener('DOMContentLoaded', () => {
    loadAIProviders();
});

// ── Upload ──
async function uploadToYouTube(jobId) {
    const privacy = prompt('Upload privacy (private/unlisted/public):', 'private');
    if (!privacy || !['private','unlisted','public'].includes(privacy)) return;
    toast('Uploading to YouTube...', '');
    try {
        const resp = await fetch('/api/upload', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ job_id: jobId, privacy })
        });
        const data = await resp.json();
        if (resp.ok) {
            toast(`Uploaded! ${data.url}`, 'success');
        } else {
            toast(`Upload failed: ${data.error}`, 'error');
        }
    } catch(e) {
        toast(`Upload error: ${e.message}`, 'error');
    }
}

// ── Pipeline ──
// ── CSV Bulk Import ──

let _csvParsedTopics = [];

function downloadCsvTemplate() {
    const header = 'topic,category,domain,structure,format,theme,voice,priority';
    const rows = [
        'How CRISPR works,biology,biology_reel,social_reel,instagram_reel,wong,aria,1',
        'Quantum computing explained,cs,cs_reel,social_reel,tiktok,npg,guy,2',
        'The mRNA vaccine mechanism,biology,,explainer,youtube_short,wong,jenny,1',
    ];
    const blob = new Blob([[header, ...rows].join('\\n')], {type: 'text/csv'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'manimator_topics.csv';
    a.click();
}

async function csvFileSelected() {
    const input = document.getElementById('csvFileInput');
    if (!input.files.length) return;
    const file = input.files[0];
    const csvText = await file.text();

    const fd = new FormData();
    fd.append('file', file);

    const resp = await fetch('/api/pipeline/import-csv?action=preview', {method: 'POST', body: fd});
    const data = await resp.json();

    if (!resp.ok || data.error) {
        document.getElementById('csvPreviewArea').style.display = 'none';
        showToast('CSV error: ' + (data.error || 'Unknown'), 'error');
        return;
    }

    _csvParsedTopics = data.topics;

    // Summary
    const cats = data.categories || {};
    const catStr = Object.entries(cats).map(([k,v]) => `${k} (${v})`).join(', ');
    document.getElementById('csvSummary').innerHTML =
        `<strong>${data.count}</strong> topics · Categories: ${catStr}`;

    // Table
    const cols = ['#', 'topic', 'category', 'domain', 'format', 'theme', 'voice', 'priority'];
    document.getElementById('csvPreviewHead').innerHTML =
        '<tr>' + cols.map(c => `<th style="padding:4px 8px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap">${c}</th>`).join('') + '</tr>';
    document.getElementById('csvPreviewBody').innerHTML =
        data.topics.map((t, i) =>
            '<tr style="border-bottom:1px solid var(--border)">' +
            `<td style="padding:3px 8px;color:var(--text-muted)">${i+1}</td>` +
            `<td style="padding:3px 8px;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${(t.topic||'').replace(/"/g,'&quot;')}">${t.topic||''}</td>` +
            `<td style="padding:3px 8px">${t.category||''}</td>` +
            `<td style="padding:3px 8px;color:var(--text-muted)">${t.domain||''}</td>` +
            `<td style="padding:3px 8px">${t.format||''}</td>` +
            `<td style="padding:3px 8px">${t.theme||''}</td>` +
            `<td style="padding:3px 8px">${t.voice||''}</td>` +
            `<td style="padding:3px 8px">${t.priority||0}</td>` +
            '</tr>'
        ).join('');

    // Warnings
    const warns = (data.warnings || []).flatMap(w => (w.warnings || []).map(m => `Row ${w.row} (${w.topic}): ${m}`));
    document.getElementById('csvWarnings').innerHTML = warns.length
        ? '⚠ ' + warns.join('<br>⚠ ')
        : '';

    document.getElementById('csvPreviewArea').style.display = 'block';
    document.getElementById('csvImportStatus').textContent = '';
}

async function importCsv() {
    if (!_csvParsedTopics.length) return;
    const btn = document.getElementById('csvImportBtn');
    const status = document.getElementById('csvImportStatus');
    btn.disabled = true;
    status.textContent = 'Adding…';

    try {
        // Re-use the add-topics endpoint directly with pre-parsed topics
        const resp = await fetch('/api/pipeline/add-topics', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({topics: _csvParsedTopics}),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) throw new Error(data.error || 'Import failed');
        status.textContent = `✓ ${data.imported} topics queued`;
        showToast(`${data.imported} topics added to pipeline`, 'success');
        loadPipelineStatus();
    } catch(e) {
        status.textContent = '✗ ' + e.message;
        showToast('Import failed: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

async function loadPipelineStatus() {
    try {
        const resp = await fetch('/api/pipeline/status');
        const data = await resp.json();
        const el = document.getElementById('pipelineStatus');
        if (!el) return;
        el.innerHTML = Object.entries(data).map(([k,v]) =>
            `<span style="margin-right:16px"><strong>${k}:</strong> ${v}</span>`
        ).join('');
    } catch(e) { /* ignore */ }
}

async function loadPipelineVideos() {
    try {
        const resp = await fetch('/api/pipeline/videos?limit=20');
        const videos = await resp.json();
        const el = document.getElementById('pipelineVideos');
        if (!el) return;
        if (!videos.length) { el.innerHTML = '<em>No videos yet</em>'; return; }
        el.innerHTML = '<table style="width:100%;font-size:13px"><tr><th>Topic</th><th>Category</th><th>Status</th><th>URL</th></tr>' +
            videos.map(v => `<tr><td>${v.topic||''}</td><td style="color:var(--text-muted)">${v.category||''}</td><td>${v.status}</td><td>${v.youtube_url ? '<a href="'+v.youtube_url+'" target="_blank">▶ Watch</a>' : '-'}</td></tr>`).join('') +
            '</table>';
    } catch(e) { /* ignore */ }
}

// ── Analytics ──
async function loadAnalyticsSummary() {
    const el = document.getElementById('analyticsSummary');
    if (!el) return;

    try {
        // Fetch summary + domain breakdown + top videos in parallel
        const [summaryResp, domainsResp, topResp] = await Promise.all([
            fetch('/api/analytics/summary'),
            fetch('/api/analytics/domains?days=30'),
            fetch('/api/analytics/top?metric=views&limit=5&days=30')
        ]);
        const data = await summaryResp.json();
        const domains = await domainsResp.json();
        const topVideos = await topResp.json();

        const hasData = data.total_videos > 0;

        if (!hasData) {
            el.innerHTML = `
                <div style="text-align:center;padding:40px 20px;color:var(--text-muted)">
                    <div style="font-size:36px;opacity:0.3;margin-bottom:12px">&#x1F4CA;</div>
                    <div style="font-size:14px;font-weight:600;margin-bottom:6px;color:var(--text)">No analytics data yet</div>
                    <div style="font-size:12px;line-height:1.6">
                        Upload videos to YouTube, then click <strong>Sync</strong> to pull metrics.<br>
                        Analytics shows real YouTube data — views, CTR, watch time.
                    </div>
                    <button class="btn btn-sm btn-primary" onclick="syncAnalytics()" style="margin-top:16px">Sync from YouTube</button>
                </div>`;
            return;
        }

        // ── Summary Cards ──
        const fmtNum = n => n >= 1000000 ? (n/1000000).toFixed(1)+'M' : n >= 1000 ? (n/1000).toFixed(1)+'K' : n;
        let html = `
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:20px">
            <div style="padding:14px;border-radius:10px;background:var(--bg-card);border:1px solid var(--border)">
                <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted)">Total Views</div>
                <div style="font-size:22px;font-weight:800;color:var(--navy);margin-top:4px">${fmtNum(data.total_views||0)}</div>
            </div>
            <div style="padding:14px;border-radius:10px;background:var(--bg-card);border:1px solid var(--border)">
                <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted)">Videos</div>
                <div style="font-size:22px;font-weight:800;color:var(--navy);margin-top:4px">${data.total_videos||0}</div>
            </div>
            <div style="padding:14px;border-radius:10px;background:var(--bg-card);border:1px solid var(--border)">
                <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted)">Avg CTR</div>
                <div style="font-size:22px;font-weight:800;color:var(--navy);margin-top:4px">${((data.avg_ctr||0)*100).toFixed(1)}%</div>
            </div>
            <div style="padding:14px;border-radius:10px;background:var(--bg-card);border:1px solid var(--border)">
                <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted)">Avg Views/Video</div>
                <div style="font-size:22px;font-weight:800;color:var(--navy);margin-top:4px">${fmtNum(Math.round(data.avg_views_per_video||0))}</div>
            </div>
            <div style="padding:14px;border-radius:10px;background:var(--bg-card);border:1px solid var(--border)">
                <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted)">Best Day</div>
                <div style="font-size:16px;font-weight:700;color:var(--navy);margin-top:6px">${data.best_posting_day||'-'}</div>
            </div>
            <div style="padding:14px;border-radius:10px;background:var(--bg-card);border:1px solid var(--border)">
                <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted)">Data Freshness</div>
                <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-top:6px">${data.data_freshness ? new Date(data.data_freshness).toLocaleDateString() : '-'}</div>
            </div>
        </div>`;

        // ── Domain Performance Bars ──
        const domainEntries = Object.entries(domains);
        if (domainEntries.length > 0) {
            const maxViews = Math.max(...domainEntries.map(([,d]) => d.avg_views || 0), 1);
            const domainColors = {
                biology_reel: '#059669', biology_mechanism: '#10b981',
                cs_reel: '#4338ca', cs_algorithm: '#4f6ef7',
                math_reel: '#c2410c', math_concept: '#f97316',
                paper_review: '#7c3aed'
            };
            html += `<div style="margin-bottom:20px">
                <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted);margin-bottom:10px">Views by Domain (30 days)</div>`;
            for (const [domain, perf] of domainEntries.sort((a,b) => (b[1].avg_views||0) - (a[1].avg_views||0))) {
                const pct = Math.max(4, ((perf.avg_views||0) / maxViews) * 100);
                const color = domainColors[domain] || 'var(--accent)';
                html += `<div style="margin-bottom:8px">
                    <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px">
                        <span style="font-weight:600;color:var(--text)">${domain.replace(/_/g,' ')}</span>
                        <span style="color:var(--text-muted)">${fmtNum(Math.round(perf.avg_views||0))} avg · ${perf.count} videos · ${((perf.avg_ctr||0)*100).toFixed(1)}% CTR</span>
                    </div>
                    <div style="height:8px;background:var(--bg-card);border-radius:4px;overflow:hidden">
                        <div style="height:100%;width:${pct}%;background:${color};border-radius:4px;transition:width 0.5s"></div>
                    </div>
                </div>`;
            }
            html += `</div>`;
        }

        // ── Top Videos Table ──
        if (Array.isArray(topVideos) && topVideos.length > 0) {
            html += `<div>
                <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted);margin-bottom:10px">Top Videos (30 days)</div>
                <table style="width:100%;font-size:12px;border-collapse:collapse">
                    <thead><tr style="border-bottom:1px solid var(--border)">
                        <th style="text-align:left;padding:6px 8px;font-weight:600;color:var(--text-muted)">Topic</th>
                        <th style="text-align:left;padding:6px 8px;font-weight:600;color:var(--text-muted)">Domain</th>
                        <th style="text-align:right;padding:6px 8px;font-weight:600;color:var(--text-muted)">Views</th>
                        <th style="text-align:center;padding:6px 8px;font-weight:600;color:var(--text-muted)">Link</th>
                    </tr></thead><tbody>`;
            for (const v of topVideos) {
                html += `<tr style="border-bottom:1px solid var(--border-subtle)">
                    <td style="padding:8px;font-weight:500;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${v.topic||'-'}</td>
                    <td style="padding:8px;color:var(--text-muted)">${(v.domain||'-').replace(/_/g,' ')}</td>
                    <td style="padding:8px;text-align:right;font-weight:600;font-family:'JetBrains Mono',monospace">${fmtNum(v.total_views||0)}</td>
                    <td style="padding:8px;text-align:center">${v.youtube_url ? '<a href="'+v.youtube_url+'" target="_blank" style="color:var(--accent);text-decoration:none;font-weight:600">Watch</a>' : '-'}</td>
                </tr>`;
            }
            html += `</tbody></table></div>`;
        }

        // ── Sync Button ──
        html += `<div style="margin-top:16px;display:flex;gap:8px;align-items:center">
            <button class="btn btn-sm" onclick="syncAnalytics()">Sync from YouTube</button>
            <span id="syncStatus" style="font-size:11px;color:var(--text-muted)"></span>
        </div>`;

        el.innerHTML = html;
    } catch(e) {
        el.innerHTML = `<div style="text-align:center;padding:30px;color:var(--text-muted)">
            <div style="font-size:13px">Could not load analytics</div>
            <div style="font-size:11px;margin-top:4px">${e.message || 'Unknown error'}</div>
        </div>`;
    }
}

async function syncAnalytics() {
    const status = document.getElementById('syncStatus');
    if (status) status.textContent = 'Syncing...';
    try {
        const resp = await fetch('/api/analytics/sync', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({days: 7})
        });
        const data = await resp.json();
        if (resp.ok) {
            if (status) status.textContent = `Synced ${data.synced} metric rows`;
            toast('Analytics synced', 'success');
            loadAnalyticsSummary(); // Refresh the view
        } else {
            if (status) status.textContent = data.error || 'Sync failed';
            toast('Sync failed: ' + (data.error || 'Unknown'), 'error');
        }
    } catch(e) {
        if (status) status.textContent = 'Sync error';
        toast('Sync error: ' + e.message, 'error');
    }
}

// ── Toast ──
function toast(msg, type = '') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `toast show ${type}`;
    setTimeout(() => el.classList.remove('show'), 3500);
}
const showToast = toast;

// (sidebar resize removed — left panel is collapse-only now)
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
