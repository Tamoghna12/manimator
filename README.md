# manimator

Dual-engine scientific video generator. Manim for landscape (16:9, 1:1), HTML/CSS + Playwright for portrait (9:16).

## What it does

Takes a JSON storyboard and renders it into a production-quality video with optional AI narration. Supports 11 scene types (hook, title, bullet list, flowchart, bar chart, scatter plot, comparison table, two-panel, equation, pipeline diagram, closing) across 7 domain templates (biology, CS, math).

**Landscape videos** use [Manim Community Edition](https://www.manim.community/) for mathematical animations.
**Portrait videos** (Instagram Reels, TikTok, YouTube Shorts) use HTML/CSS animations captured frame-by-frame via Playwright with the Web Animations API for frame-perfect timing. Output is **60 fps WebM** encoded in VP9 constant-quality mode (CRF 18) for sharp text and smooth motion at any screen size.

**Content engine** provides a batch pipeline (topic queue → LLM generation → render → YouTube upload) with SQLite persistence, YouTube Analytics integration, and quota-safe upload management.

## Install

### Docker (recommended — works on all platforms)

Docker is the easiest way to run manimator on **Windows, macOS, and Linux**. It bundles all system dependencies (ffmpeg, Cairo, Pango, fonts, Chromium) so you don't need to install them manually.

**Prerequisites:**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or Docker Engine (Linux)
- On Windows, make sure Docker Desktop is running before proceeding

**Build and run:**

```bash
# Clone the repo
git clone https://github.com/Tamoghna12/manimator.git
cd manimator

# Build the image
docker build -t manimator .

# Run the web UI
docker run -p 5100:5100 -v ./output:/app/manimator_output manimator
```

Open http://localhost:5100 in your browser.

**Windows (PowerShell):**

```powershell
# Clone
git clone https://github.com/Tamoghna12/manimator.git
cd manimator

# Build
docker build -t manimator .

# Run (use ${PWD} for volume mount on Windows)
docker run -p 5100:5100 -v "${PWD}/output:/app/manimator_output" manimator
```

**Windows (Command Prompt):**

```cmd
git clone https://github.com/Tamoghna12/manimator.git
cd manimator

docker build -t manimator .

docker run -p 5100:5100 -v "%cd%/output:/app/manimator_output" manimator
```

**With docker compose:**

```bash
docker compose up --build
```

**Pass API keys for AI generation:**

```bash
# Linux/macOS
docker run -p 5100:5100 \
  -v ./output:/app/manimator_output \
  -e OPENAI_API_KEY=sk-... \
  manimator

# Windows PowerShell
docker run -p 5100:5100 `
  -v "${PWD}/output:/app/manimator_output" `
  -e OPENAI_API_KEY=sk-... `
  manimator
```

You can also enter API keys directly in the web UI without setting environment variables.

**Render a video via CLI (Docker):**

```bash
docker run -v ./output:/app/manimator_output -v ./my_storyboard.json:/app/input.json \
    manimator manimator.portrait -s /app/input.json --narrate -o /app/manimator_output/out.webm
```

### Native install (Linux/macOS)

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

# macOS (Homebrew)
# brew install ffmpeg cairo pango

# Optional: install fonts for portrait videos
mkdir -p ~/.local/share/fonts
# Download Inter and JetBrains Mono from Google Fonts, copy .ttf files there
fc-cache -fv
```

### Native install (Windows — without Docker)

If you prefer not to use Docker on Windows, you can install natively. This requires more manual setup.

**1. Install Python 3.10+**

Download from https://www.python.org/downloads/ and check "Add Python to PATH" during installation.

**2. Install ffmpeg**

```powershell
# Option A: Using winget (Windows 11 / Windows 10 with App Installer)
winget install Gyan.FFmpeg

# Option B: Using Chocolatey
choco install ffmpeg

# Option C: Manual install
# Download from https://www.gyan.dev/ffmpeg/builds/
# Extract and add the bin/ folder to your system PATH
```

Verify: `ffmpeg -version`

**3. Install GTK3 runtime (provides Cairo and Pango)**

Download and install the GTK3 runtime from https://github.com/nickvdp/gtk3-win/releases — this provides the `libcairo` and `libpango` DLLs that Manim needs.

Alternatively, install via MSYS2:
```powershell
# Install MSYS2 from https://www.msys2.org/
# Then in an MSYS2 terminal:
pacman -S mingw-w64-x86_64-cairo mingw-w64-x86_64-pango
# Add C:\msys64\mingw64\bin to your system PATH
```

**4. Install manimator**

```powershell
git clone https://github.com/Tamoghna12/manimator.git
cd manimator

pip install -e ".[dev]"

# Install Playwright browser
playwright install chromium
```

**5. Run**

```powershell
python -m manimator.web
# Opens at http://localhost:5100
```

### Supported LLM providers

| Provider | Models | API key env var |
|----------|--------|-----------------|
| OpenAI | gpt-4o, gpt-4o-mini | `OPENAI_API_KEY` |
| Anthropic | claude-sonnet-4-20250514, claude-haiku-4-5-20251001 | `ANTHROPIC_API_KEY` |
| Google Gemini | gemini-2.5-flash, gemini-2.0-flash | `GOOGLE_API_KEY` |
| ZhipuAI (Z.AI) | glm-5, glm-5-turbo, glm-4.7, glm-4.7-FlashX, glm-4.7-Flash | `ZHIPUAI_API_KEY` |
| Ollama | llama3.2, mistral, qwen2.5, gemma3, phi4, any local model | _(no key needed)_ |
| OpenAI-compatible | Any (Groq, Together, etc.) | `OPENAI_API_KEY` + base URL |

**ZhipuAI (Z.AI):** Uses the OpenAI-compatible endpoint at `https://api.z.ai/api/paas/v4/` — no separate SDK required. Get your API key from https://open.bigmodel.cn/. The **GLM Coding Pro** plan includes access to `glm-5`, `glm-5-turbo`, `glm-4.7`, `glm-4.7-FlashX`, and `glm-4.7-Flash`.

**Ollama:** Runs models locally on your machine — no API key or internet required after the initial model download. See the [Ollama section](#ollama-local-models) below for setup.

All providers can be selected in the web UI dropdown. API keys can be entered in the UI or set as environment variables.

### Ollama (local models)

Ollama lets you run LLMs locally for storyboard generation — no API key, no cost, no data leaving your machine.

#### 1. Install Ollama

**Windows:** Download and run the installer from https://ollama.com/download

**macOS:**
```bash
brew install ollama
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### 2. Pull a model

```bash
# Fast and capable (recommended for storyboards)
ollama pull llama3.2

# Other good options
ollama pull mistral
ollama pull qwen2.5
ollama pull gemma3
ollama pull phi4
```

#### 3. Start Ollama server

```bash
ollama serve
# Runs at http://localhost:11434
```

On Windows and macOS, Ollama starts automatically after install. On Linux, you may need to start it manually or enable the systemd service:

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

#### 4. Use in the web UI

Select **Ollama (Local)** from the provider dropdown. The base URL auto-fills to `http://localhost:11434/v1`. Pick a model from the list (or type any model name you have pulled), leave the API key blank, and click **Generate**.

#### 5. Docker + Ollama (Linux)

When manimator runs inside Docker, `localhost` refers to the container, not your host machine. Use `host.docker.internal` instead:

```bash
# Add --add-host flag so the container can reach Ollama on your host
sudo docker run -d \
  -p 5300:5300 \
  -v ./output:/app/manimator_output \
  -e MANIMATOR_HOST=0.0.0.0 \
  -e MANIMATOR_PORT=5300 \
  --add-host=host.docker.internal:host-gateway \
  --name manimator \
  manimator
```

Then in the web UI, set the Ollama base URL to:
```
http://host.docker.internal:11434/v1
```

On **Windows and macOS**, `host.docker.internal` works automatically — no `--add-host` flag needed.

#### Ollama tips

- Use `ollama list` to see which models you have pulled
- Larger models (7B+) produce better storyboard JSON but are slower; `llama3.2` (3B) is a good balance
- If generation returns malformed JSON, try a larger model or add `--max-retries 2` in the CLI
- Ollama uses GPU automatically if available (NVIDIA/AMD/Apple Silicon)

### YouTube integration (optional)

Required only for upload and analytics features.

```bash
pip install -e ".[youtube]"
```

**Setup OAuth credentials:**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Desktop application)
3. Enable the YouTube Data API v3 and YouTube Analytics API
4. Download `client_secret.json`:
   - **Linux/macOS:** `~/.config/manimator/client_secret.json`
   - **Windows:** `%USERPROFILE%\.config\manimator\client_secret.json`

On first upload, a browser window opens for OAuth consent. The refresh token is stored at `youtube_token.json` in the same directory.

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
- AI storyboard generation (select provider, enter API key, type a topic)
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

## Output quality

Portrait renders target production-level social media quality:

| Setting | Value | Notes |
|---------|-------|-------|
| Resolution | 1080 × 1920 | Native portrait (9:16) |
| Frame rate | 60 fps | Smooth CSS animation capture |
| Video codec | VP9 | `-b:v 0 -crf 18` constant-quality mode |
| Encoding preset | `quality good, speed 2` | Parallel row encoding (`-row-mt 1`) |
| Audio codec | Opus | 48 kHz stereo |

### Visual design features

**All scenes:**
- Noise texture overlay (SVG fractal, `mix-blend-mode: overlay`) adds film-grain depth to flat backgrounds
- Vignette (radial gradient) darkens edges for a cinematic feel
- Rich diagonal gradients (`160deg`, dual midpoint) instead of flat fills
- Layered multi-stop `box-shadow` on cards for tactile depth
- Colored glow shadows on callout boxes matching their accent color
- Headers at `font-weight: 900` with negative letter-spacing for editorial punch

**Hook scene:**
- Main text rendered with `-webkit-background-clip: text` gradient (white → cyan → brand blue)
- Animated "Watch This" pill badge with pulsing accent dot
- Three layered gradient orbs for depth
- Bottom accent bar with animated `gradientShift` cycling across the brand palette

**Interactive elements:**
- `popIn` spring keyframe (0 → 104% → 98% → 100%) on bullet cards, flow nodes, equation boxes — feels physical rather than flat
- `growWidth` on bar chart fills with `cubic-bezier(0.22, 1, 0.36, 1)` spring easing
- Shimmer sweep on bar fills after animation completes
- `scaleIn` entrance for dividers and accent lines

## Troubleshooting

### Windows-specific issues

**`ffmpeg` not found:** Make sure ffmpeg is on your PATH. After installing, open a new terminal and run `ffmpeg -version`. If it still doesn't work, add the ffmpeg `bin/` folder to your system PATH manually (System → Advanced → Environment Variables → Path → Edit → Add).

**Cairo/Pango DLL errors:** Manim needs Cairo and Pango. The easiest fix is to install GTK3 runtime or use MSYS2 (see native install instructions above). Make sure the DLL directory is on your system PATH.

**Long path errors:** Windows has a 260-character path limit by default. Enable long paths:
```powershell
# Run PowerShell as Administrator
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

**Permission errors with Docker:** Make sure Docker Desktop is running. If you get "access denied", right-click Docker Desktop → "Run as administrator", or add your user to the `docker-users` group.

### Linux-specific issues

**Docker permission denied:** Add your user to the docker group:
```bash
sudo usermod -aG docker $USER
# Log out and back in for the change to take effect
```

**Missing system libraries:** If pycairo fails to build:
```bash
sudo apt-get install build-essential libcairo2-dev libpango1.0-dev pkg-config python3-dev
```

### General issues

**Playwright browser not found:** Run `playwright install chromium` (or inside Docker, this is done automatically).

**AI generation fails with "No module named ...":** Make sure you have the provider's SDK installed. With Docker, the OpenAI, Anthropic, and Google SDKs are pre-installed. ZhipuAI uses the OpenAI SDK (no extra install needed).

**"No video files to concatenate":** This means scene rendering failed before the concatenation step. Check the full error log above this message for the actual rendering error (usually a missing dependency or invalid storyboard JSON).

**Ollama not reachable from Docker (Linux):** If Ollama is running on your host but the container can't reach it, add `--add-host=host.docker.internal:host-gateway` to your `docker run` command and use `http://host.docker.internal:11434/v1` as the base URL in the web UI. On Windows/macOS this works automatically.

**Ollama returns invalid JSON:** The model may be too small to reliably follow the storyboard schema. Try `llama3.2` (3B) or larger. You can also retry — the UI will automatically send the error back to the model for correction.

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
│   ├── html_scenes.py     # HTML/CSS scene templates (11 types, 60fps, noise+vignette)
│   ├── renderer.py        # Frame-by-frame capture + VP9 CQ ffmpeg encoding
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
ai = ["openai>=1.0", "anthropic>=0.30", "google-genai>=1.0"]
youtube = ["google-api-python-client>=2.100", "google-auth-oauthlib>=1.0", "google-auth-httplib2>=0.2"]
```

## License

MIT
