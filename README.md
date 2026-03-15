# manimator

Dual-engine scientific video generator. Manim for landscape (16:9, 1:1), HTML/CSS + Playwright for portrait (9:16).

## What it does

Takes a JSON storyboard and renders it into a production-quality video with optional AI narration. Supports 11 scene types (hook, title, bullet list, flowchart, bar chart, scatter plot, comparison table, two-panel, equation, pipeline diagram, closing) across 7 domain templates (biology, CS, math).

**Landscape videos** use [Manim Community Edition](https://www.manim.community/) for mathematical animations.
**Portrait videos** (Instagram Reels, TikTok, YouTube Shorts) use HTML/CSS animations captured frame-by-frame via Playwright with the Web Animations API for frame-perfect timing.

**Content engine** provides a batch pipeline (topic queue → LLM generation → render → YouTube upload) with SQLite persistence, YouTube Analytics integration, and quota-safe upload management.

## Install

```bash
# Clone
git clone https://github.com/Tamoghna12/manimator.git
cd manimator

# Install with dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Install system dependencies (Ubuntu/Debian)
sudo apt-get install ffmpeg libcairo2-dev libpango1.0-dev

# Optional: install fonts for portrait videos
mkdir -p ~/.local/share/fonts
# Download Inter and JetBrains Mono from Google Fonts, copy .ttf files there
fc-cache -fv
```

### Docker (recommended)

```bash
# Build and run
docker compose up --build

# Or without compose
docker build -t manimator .
docker run -p 5100:5100 -v ./output:/app/manimator_output manimator

# Render a video via CLI
docker run -v ./output:/app/manimator_output -v ./my_storyboard.json:/app/input.json \
    manimator manimator.portrait -s /app/input.json --narrate -o /app/manimator_output/out.webm
```

### YouTube integration (optional)

Required only for upload and analytics features.

```bash
pip install -e ".[youtube]"
```

**Setup OAuth credentials:**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Desktop application)
3. Enable the YouTube Data API v3 and YouTube Analytics API
4. Download `client_secret.json` to `~/.config/manimator/client_secret.json`

On first upload, a browser window opens for OAuth consent. The refresh token is stored at `~/.config/manimator/youtube_token.json` (permissions `0600`).

**Quota:** YouTube Data API defaults to 10,000 units/day. Each upload costs ~1,600 units, limiting you to ~6 uploads/day. The pipeline enforces this limit automatically. Request a quota increase via Google Cloud Console if needed.

**OAuth consent screen:** In "Testing" mode, limited to 100 authorized users. Move to "Production" for broader access.

## Quick start

### Web UI

```bash
python -m manimator.web
# Opens at http://localhost:5100
```

The web UI provides:
- Template browser organized by domain (biology, CS, math)
- Live HTML preview of each scene
- JSON editor with validation
- LLM prompt generator (copy prompt → paste into Claude/ChatGPT → paste JSON back)
- Background rendering with progress tracking
- YouTube upload button (appears after successful render)
- Pipeline dashboard (topic queue, batch run status, video list)
- Analytics dashboard (total views, top videos, best domain, CTR)

### CLI — Portrait video (Instagram/TikTok)

```bash
# Render a storyboard with narration
python -m manimator.portrait -s crispr_reel.json --narrate --voice guy

# Specify format
python -m manimator.portrait -s story.json --format tiktok --narrate
```

### CLI — Landscape video (Manim)

```bash
# High quality render with narration
python -m manimator.orchestrator -s gradient_descent.json --narrate -q high

# Quick preview
python -m manimator.orchestrator -s story.json -q low
```

### CLI — Storyboard authoring

```bash
# List available templates and structures
python -m manimator.storyboard_cli list

# Generate an LLM prompt for a topic
python -m manimator.storyboard_cli prompt "How CRISPR works" --domain biology_reel

# Create a scaffold from a structure
python -m manimator.storyboard_cli scaffold --structure social_reel --topic "My Topic" -o my_video.json

# Load a ready-to-render example
python -m manimator.storyboard_cli example --domain cs_reel -o transformers_reel.json

# Validate a storyboard
python -m manimator.storyboard_cli validate my_video.json

# Generate storyboard using AI
python -m manimator.storyboard_cli generate "How CRISPR works" --provider openai --domain biology_reel --render
```

### CLI — Content pipeline

Batch-generate videos from a topic queue. State persists in SQLite at `~/.local/share/manimator/pipeline.db`.

#### With LLM (auto-generate storyboards)

```bash
# Create a topics file (one topic per line, # for comments)
cat > topics.txt << 'EOF'
How CRISPR-Cas9 gene editing works
The biochemistry of mRNA vaccines
Why mitochondria are the powerhouse of the cell
EOF

# Add topics to the queue
python -m manimator.storyboard_cli pipeline add-topics topics.txt --domain biology_reel --format instagram_reel

# Run the pipeline (generate + render, no upload)
python -m manimator.storyboard_cli pipeline run --provider openai --limit 5

# Run with upload to YouTube
python -m manimator.storyboard_cli pipeline run --provider openai --limit 3 --upload --privacy private --narrate

# Check status
python -m manimator.storyboard_cli pipeline status

# List completed videos
python -m manimator.storyboard_cli pipeline list --status done
```

#### Without LLM (manual storyboards — no API keys needed)

If you write storyboard JSONs by hand (e.g. with the web UI scaffold tool, or copied from an example), you can batch-render them without any LLM provider or API costs.

```bash
# Import one or more storyboard JSON files
python -m manimator.storyboard_cli pipeline add-storyboards story1.json story2.json

# Import an entire directory of JSONs
python -m manimator.storyboard_cli pipeline add-storyboards ./storyboards/ --domain biology_reel

# Render all queued storyboards (no LLM required)
python -m manimator.storyboard_cli pipeline render --limit 10

# Render and upload to YouTube
python -m manimator.storyboard_cli pipeline render --limit 5 --upload --privacy private --narrate
```

**Workflow:**
1. Use the web UI (`/`) to preview scenes and build a storyboard with the JSON editor
2. Use `manimator-storyboard scaffold` to get a template and fill in your content manually
3. `pipeline add-storyboards` validates each file (Pydantic schema check) and queues them
4. `pipeline render` renders the queue — no LLM, no internet connection required

This path is useful for research educators, conference presenters, or anyone who prefers full control over content without delegating to a language model.

### CLI — YouTube upload

Upload a single rendered video. Uses `social.generate_post_copy()` for metadata when a storyboard is provided.

```bash
# Upload with auto-generated metadata from storyboard
python -m manimator.storyboard_cli upload video.webm --storyboard story.json --privacy private

# Upload with manual title
python -m manimator.storyboard_cli upload video.webm --title "How CRISPR Works" --privacy unlisted
```

### CLI — YouTube Analytics

Sync metrics from the YouTube Analytics API and view performance insights.

```bash
# Sync last 7 days of metrics
python -m manimator.storyboard_cli analytics sync --days 7

# Top videos by views
python -m manimator.storyboard_cli analytics top --metric views --days 30

# Summary insights
python -m manimator.storyboard_cli analytics insights
```

**Note:** YouTube Analytics data lags 48-72 hours behind real-time. The "best posting day" insight uses only first-day metrics per video as a proxy for upload day to avoid conflating accumulation patterns with posting day effects (cf. Kohavi et al., 2020, *Trustworthy Online Controlled Experiments*, Cambridge University Press).

## Storyboard format

A storyboard is a JSON file with two sections:

```json
{
  "meta": {
    "title": "How CRISPR Works",
    "color_theme": "wong",
    "format": "instagram_reel",
    "resolution": [1080, 1920]
  },
  "scenes": [
    {
      "type": "hook",
      "id": "opener",
      "hook_text": "Scientists can now edit ANY gene in your DNA",
      "subtitle": "Here's how CRISPR works"
    },
    {
      "type": "bullet_list",
      "id": "components",
      "header": "Core Components",
      "items": [
        "Guide RNA: 20-nt spacer complementary to target",
        "Cas9 nuclease: cuts both DNA strands",
        "PAM sequence: required for recognition"
      ]
    }
  ]
}
```

### Scene types

| Type | Description |
|------|-------------|
| `hook` | Bold text on dark background (social openers) |
| `title` | Title card with subtitle and footnote |
| `bullet_list` | Header + bullet points + optional callout |
| `flowchart` | Process flow with connected stages |
| `bar_chart` | Labeled bar chart with values |
| `scatter_plot` | XY scatter with labeled clusters |
| `comparison_table` | Side-by-side comparison grid |
| `two_panel` | Split view with left/right content |
| `equation` | Mathematical formula display |
| `pipeline_diagram` | System architecture diagram |
| `closing` | References and call-to-action |

### Color themes

- **wong** — Nature Methods standard (default, colorblind-safe)
- **npg** — Nature Publishing Group palette
- **tol_bright** — High contrast for presentations

## Content engine

The content engine closes the loop from topic ideation to performance measurement:

```
Topics → Pipeline → LLM Generation → Render → Upload → Analytics → Iterate
```

### Pipeline (`manimator/pipeline.py`)

SQLite-backed batch processor. Persists all state so runs can be interrupted and resumed.

**Database:** `~/.local/share/manimator/pipeline.db`
**Renders:** `~/.local/share/manimator/renders/{video_id}.webm`

**Tables:**
- `topics` — Queue of topics with domain, structure, format, theme, priority
- `videos` — Generated videos with status tracking (queued → generating → rendering → uploading → done/failed)

**Status lifecycle:**

```
  LLM path:
  topic (unused) ──▶ generating ──▶ rendering ──▶ uploading ──▶ done
                          │               │              │
                          ▼               ▼              ▼
                        failed          failed         failed
                          └──────────────┴──────────────┘
                                         │
                                   retry_failed() ──▶ queued

  No-LLM path:
  add_storyboards() ──▶ queued ──▶ rendering ──▶ [uploading] ──▶ done
```

**Resilience features:**
- **Stale recovery:** Videos stuck in `generating`/`rendering`/`uploading` for >15 minutes are auto-reset to `failed` on next `run_pipeline()` call. Prevents orphaned state from crashed runs.
- **Quota guard:** Checks daily upload count before each upload. Raises `RuntimeError` at 6 uploads/day (YouTube's default quota limit).
- **WAL mode:** SQLite Write-Ahead Logging for safe concurrent access from the Flask thread pool.
- **Per-video error isolation:** Individual failures are recorded and don't halt the batch.

### Uploader (`manimator/uploader.py`)

YouTube Data API v3 integration with OAuth2 and lazy SDK imports.

**Features:**
- Resumable upload with 10MB chunks (`MediaFileUpload`)
- Auto-generated metadata via `social.generate_post_copy()` for shorts
- Auto-thumbnail extraction via `renderer.generate_thumbnail()`
- Title truncation (100 char YouTube limit)
- Privacy validation (private/unlisted/public)
- Token stored with restrictive permissions (`chmod 600`)

**Scopes requested:**
- `youtube.upload` — Video uploads
- `youtube.readonly` — Channel info
- `yt-analytics.readonly` — Performance metrics

### Analytics (`manimator/analytics.py`)

YouTube Analytics API v2 integration for performance tracking.

**Metrics synced (per-video, per-day):**
views, likes, comments, shares, watch time (minutes), average view duration (seconds), impressions, click-through rate

**Insight functions:**
- `get_video_stats(video_id)` — Aggregated stats for a single video
- `get_top_videos(metric, limit, days)` — Top N videos by any metric
- `get_domain_performance(days)` — Per-domain aggregation (count, total views, avg views, avg CTR)
- `get_insights()` — Summary dashboard: total videos/views, best/worst domain, best video, best posting day, avg CTR, data freshness

### Web API routes

| Route | Method | Description |
|-------|--------|-------------|
| `/api/upload` | POST | Upload completed render to YouTube |
| `/api/pipeline/status` | GET | Pipeline status counts |
| `/api/pipeline/videos` | GET | List videos (optional `?status=done`) |
| `/api/pipeline/add-topics` | POST | Add topics to queue (LLM path) |
| `/api/pipeline/run` | POST | Trigger batch LLM generate + render |
| `/api/pipeline/add-storyboards` | POST | Import pre-written storyboard JSONs (no LLM) |
| `/api/pipeline/render` | POST | Render queued storyboards (no LLM) |
| `/api/analytics/summary` | GET | Analytics insights summary |
| `/api/analytics/top` | GET | Top videos by metric |
| `/api/analytics/sync` | POST | Sync metrics from YouTube |

## Architecture

```
manimator/
├── schema.py              # Pydantic v2 storyboard validation
├── config.py              # Themes, palettes, typography
├── codegen.py             # JSON → Manim Python code generation
├── renderer.py            # Manim scene rendering + concatenation
├── orchestrator.py        # Landscape video CLI pipeline
├── narration.py           # edge-tts / gTTS voice synthesis
├── subtitles.py           # SRT subtitle generation + burn-in
├── social.py              # Social media format profiles + post copy
├── helpers.py             # Manim UI components (cards, bullets, charts)
├── topic_templates.py     # Structures, schemas, domain templates, LLM prompts
├── llm.py                 # Multi-provider LLM integration (lazy imports)
├── storyboard_cli.py      # Storyboard authoring + pipeline + analytics CLI
├── pipeline.py            # Batch pipeline with SQLite persistence
├── uploader.py            # YouTube OAuth2 upload (lazy Google SDK)
├── analytics.py           # YouTube Analytics sync + insights
├── templates/             # Manim scene type renderers (one per type)
├── portrait/
│   ├── html_scenes.py     # HTML/CSS scene templates (11 types)
│   ├── renderer.py        # Frame-by-frame capture + ffmpeg encoding
│   └── orchestrator.py    # Portrait video CLI pipeline
└── web/
    ├── app.py             # Flask web UI + API (23 routes)
    └── __main__.py        # Web server entry point
```

### Data flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Content Engine                                │
│                                                                      │
│  ── LLM path ──────────────────────────────────────────────────────  │
│  topics.txt ──▶ Pipeline.add_topics() ──▶ SQLite (topics table)     │
│  Pipeline.run_pipeline()                                             │
│    ├── llm.generate_storyboard() ──▶ SQLite (storyboard_json)      │
│    ├── subprocess (portrait/orchestrator) ──▶ renders/{id}.webm     │
│    └── uploader.upload_short() ──▶ YouTube ──▶ SQLite (youtube_id)  │
│                                                                      │
│  ── No-LLM path (no API keys required) ───────────────────────────  │
│  story.json ──▶ Pipeline.add_storyboards() ──▶ SQLite (queued)     │
│  Pipeline.run_renders()                                              │
│    ├── subprocess (portrait/orchestrator) ──▶ renders/{id}.webm     │
│    └── [optional] uploader.upload_short() ──▶ YouTube               │
│                                                                      │
│  Analytics.sync_metrics() ──▶ YouTube Analytics API ──▶ SQLite      │
│  Analytics.get_insights() ──▶ domain performance, top videos, CTR   │
└──────────────────────────────────────────────────────────────────────┘
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (174 tests)
pytest tests/ -v

# Lint
ruff check manimator/

# Type check
mypy manimator/ --ignore-missing-imports
```

### Test coverage

| Module | Tests | Coverage |
|--------|-------|----------|
| `pipeline.py` | 34 (unit) | Topic CRUD, status, LLM pipeline (mocked), no-LLM add_storyboards/run_renders, stale recovery, quota guard, retry |
| `uploader.py` | 7 (unit) | Upload success/failure, privacy validation, title truncation, credentials |
| `analytics.py` | 13 (unit) | Stats aggregation, top videos, domain performance, insights, sync |
| `web/app.py` | 29 (route) | All 10 new API routes: validation, error paths, mock pipeline/analytics |

All tests use in-memory SQLite (`:memory:`) and mocked external services. No YouTube credentials required for testing.

### Optional dependency groups

```toml
[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "mypy", "ruff"]
ai = ["openai>=1.0", "anthropic>=0.30", "google-genai>=1.0", "zhipuai>=2.0"]
youtube = ["google-api-python-client>=2.100", "google-auth-oauthlib>=1.0", "google-auth-httplib2>=0.2"]
```

## License

MIT
