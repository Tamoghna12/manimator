# manimator

Dual-engine scientific video generator. Manim for landscape (16:9, 1:1), HTML/CSS + Playwright for portrait (9:16).

## What it does

Takes a JSON storyboard and renders it into a production-quality video with optional AI narration. Supports 11 scene types (hook, title, bullet list, flowchart, bar chart, scatter plot, comparison table, two-panel, equation, pipeline diagram, closing) across 7 domain templates (biology, CS, math).

**Landscape videos** use [Manim Community Edition](https://www.manim.community/) for mathematical animations.
**Portrait videos** (Instagram Reels, TikTok, YouTube Shorts) use HTML/CSS animations captured frame-by-frame via Playwright with the Web Animations API for frame-perfect timing.

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
```

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
├── storyboard_cli.py      # Storyboard authoring CLI
├── templates/             # Manim scene type renderers (one per type)
├── portrait/
│   ├── html_scenes.py     # HTML/CSS scene templates (11 types)
│   ├── renderer.py        # Frame-by-frame capture + ffmpeg encoding
│   └── orchestrator.py    # Portrait video CLI pipeline
└── web/
    ├── app.py             # Flask web UI + API
    └── __main__.py        # Web server entry point
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check manimator/

# Type check
mypy manimator/ --ignore-missing-imports
```

## License

MIT
