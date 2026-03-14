"""Generate production-quality HTML pages for portrait video scenes.

Each function returns a self-contained HTML page with CSS animations
at 1080x1920 portrait resolution. Design targets: Kurzgesagt-level
polish with gradient backgrounds, glassmorphism, smooth easing,
animated accents, and proper mobile visual hierarchy.
"""

import html
import math
import random

# ── Base CSS: shared across all scenes ────────────────────────────────────────

_BASE_CSS = """
/* Fonts loaded from local system install (no CDN dependency) */

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    width: 1080px;
    height: 1920px;
    overflow: hidden;
    font-family: 'Inter', 'Inter Variable', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
    font-feature-settings: 'kern' 1, 'liga' 1, 'calt' 1;
}

.scene {
    width: 1080px;
    height: 1920px;
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
}

/* ── Keyframes ── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(50px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
@keyframes scaleIn {
    from { opacity: 0; transform: scale(0.85); }
    to { opacity: 1; transform: scale(1); }
}
@keyframes slideInLeft {
    from { opacity: 0; transform: translateX(-80px); }
    to { opacity: 1; transform: translateX(0); }
}
@keyframes slideInRight {
    from { opacity: 0; transform: translateX(80px); }
    to { opacity: 1; transform: translateX(0); }
}
@keyframes slideInDown {
    from { opacity: 0; transform: translateY(-50px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes growWidth {
    from { width: 0; }
}
@keyframes growHeight {
    from { height: 0; }
}
@keyframes pulse {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.05); opacity: 0.9; }
}
@keyframes shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
@keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-8px); }
}
@keyframes expandLine {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
}
@keyframes rotateIn {
    from { opacity: 0; transform: rotate(-10deg) scale(0.9); }
    to { opacity: 1; transform: rotate(0) scale(1); }
}
@keyframes countUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes glowPulse {
    0%, 100% { box-shadow: 0 0 20px rgba(255,255,255,0.1); }
    50% { box-shadow: 0 0 40px rgba(255,255,255,0.2); }
}

.anim-item {
    opacity: 0;
    animation-fill-mode: forwards;
    animation-duration: 0.6s;
    animation-timing-function: cubic-bezier(0.22, 1, 0.36, 1);
}

/* ── Decorative elements ── */
.bg-grid {
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
    background-size: 60px 60px;
    pointer-events: none;
}

.bg-dots {
    position: absolute;
    inset: 0;
    background-image: radial-gradient(circle, rgba(0,0,0,0.04) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
}

.gradient-orb {
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    pointer-events: none;
    opacity: 0;
    animation: fadeIn 1.5s 0.2s forwards;
}
"""


def _esc(text: str) -> str:
    return html.escape(str(text))


def _wrap_page(body_html: str, css: str, bg_color: str = "#FAFAFA") -> str:
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>
{_BASE_CSS}
body {{ background: {bg_color}; }}
{css}
</style>
</head>
<body>{body_html}</body>
</html>"""


def _tc(theme: dict) -> dict:
    """Extract CSS-friendly colors from theme."""
    return {
        "bg": theme.get("bg_main", "#FAFAFA"),
        "bg_dark": theme.get("bg_dark", "#1a1a2e"),
        "bg_card": theme.get("bg_card", "#FFFFFF"),
        "blue": theme.get("blue", "#0173B2"),
        "orange": theme.get("orange", "#DE8F05"),
        "green": theme.get("green", "#029E73"),
        "red": theme.get("red", "#E64B35"),
        "purple": theme.get("purple", "#8491B4"),
        "cyan": theme.get("cyan", "#56B4E9"),
        "text_dark": theme.get("text_dark", "#1A1A1A"),
        "text_body": theme.get("text_body", "#333333"),
        "text_muted": theme.get("text_muted", "#999999"),
        "border": theme.get("border", "#E0E0E0"),
        "highlight": theme.get("highlight", "#FFF3CD"),
        "palette": theme.get("palette", ["#0173B2", "#DE8F05", "#029E73"]),
    }


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ══════════════════════════════════════════════════════════════════════════════
# HOOK SCENE — Bold, attention-grabbing opening
# ══════════════════════════════════════════════════════════════════════════════

def hook_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    words = data["hook_text"].split()
    subtitle = data.get("subtitle", "")

    word_spans = []
    for i, w in enumerate(words):
        delay = 0.4 + i * 0.1
        word_spans.append(
            f'<span class="anim-item hook-word" '
            f'style="animation-name: fadeInUp; animation-delay: {delay:.2f}s; '
            f'animation-duration: 0.5s">{_esc(w)}</span>'
        )
    words_html = " ".join(word_spans)
    sub_delay = 0.4 + len(words) * 0.1 + 0.4

    css = f"""
    .scene {{
        background: linear-gradient(160deg, #0a0a1a 0%, {c['bg_dark']} 40%, #0d1b2a 100%);
        justify-content: center; align-items: center; padding: 80px;
    }}
    .gradient-orb.orb1 {{ width: 600px; height: 600px; top: -100px; right: -150px;
        background: {_hex_to_rgba(c['blue'], 0.15)}; }}
    .gradient-orb.orb2 {{ width: 400px; height: 400px; bottom: 200px; left: -100px;
        background: {_hex_to_rgba(c['purple'], 0.12)}; animation-delay: 0.5s; }}
    .hook-container {{ position: relative; z-index: 2; text-align: center; }}
    .accent-line {{ width: 80px; height: 4px; border-radius: 2px; margin: 0 auto 50px;
        background: linear-gradient(90deg, {c['blue']}, {c['cyan']});
        opacity: 0; animation: scaleIn 0.5s 0.2s forwards; }}
    .hook-text {{ font-size: 76px; font-weight: 900; color: white;
        line-height: 1.2; letter-spacing: -1px;
        display: flex; flex-wrap: wrap; justify-content: center; gap: 10px 16px; }}
    .hook-word {{ display: inline-block;
        text-shadow: 0 2px 40px rgba(0,0,0,0.5); }}
    .hook-subtitle {{ font-size: 34px; font-weight: 400; letter-spacing: 2px;
        text-transform: uppercase; margin-top: 44px;
        color: {_hex_to_rgba(c['cyan'], 0.8)};
        opacity: 0; animation: fadeInUp 0.6s {sub_delay:.2f}s forwards; }}
    .bottom-accent {{ position: absolute; bottom: 0; left: 0; right: 0; height: 6px;
        background: linear-gradient(90deg, {c['blue']}, {c['green']}, {c['orange']});
        opacity: 0; animation: fadeIn 0.8s {sub_delay + 0.3:.2f}s forwards; }}
    """

    body = f"""<div class="scene">
        <div class="bg-grid"></div>
        <div class="gradient-orb orb1"></div>
        <div class="gradient-orb orb2"></div>
        <div class="hook-container">
            <div class="accent-line"></div>
            <div class="hook-text">{words_html}</div>
            {"<div class='hook-subtitle'>" + _esc(subtitle) + "</div>" if subtitle else ""}
        </div>
        <div class="bottom-accent"></div>
    </div>"""

    return _wrap_page(body, css, c["bg_dark"])


# ══════════════════════════════════════════════════════════════════════════════
# TITLE SCENE
# ══════════════════════════════════════════════════════════════════════════════

def title_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    title = _esc(data["title"])
    subtitle = _esc(data.get("subtitle", ""))
    footnote = _esc(data.get("footnote", ""))

    css = f"""
    .scene {{ background: linear-gradient(175deg, {c['bg']} 0%, #f0f4f8 100%);
              justify-content: center; align-items: center; padding: 80px; }}
    .gradient-orb.orb1 {{ width: 500px; height: 500px; top: 100px; left: -100px;
        background: {_hex_to_rgba(c['blue'], 0.08)}; }}
    .title-container {{ position: relative; z-index: 2; text-align: center; }}
    .title {{ font-size: 68px; font-weight: 900; color: {c['text_dark']};
              line-height: 1.15; letter-spacing: -1.5px;
              opacity: 0; animation: fadeInUp 0.8s 0.3s forwards; }}
    .divider {{ width: 100px; height: 5px; border-radius: 3px; margin: 40px auto;
        background: linear-gradient(90deg, {c['blue']}, {c['green']});
        transform-origin: center; opacity: 0;
        animation: scaleIn 0.5s 0.8s forwards; }}
    .subtitle {{ font-size: 36px; color: {c['text_body']}; font-weight: 400;
                 line-height: 1.5; opacity: 0; animation: fadeIn 0.6s 1.1s forwards; }}
    .footnote {{ font-size: 24px; color: {c['text_muted']}; position: absolute;
                 bottom: 140px; left: 80px; right: 80px; text-align: center;
                 opacity: 0; animation: fadeIn 0.5s 1.5s forwards; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="gradient-orb orb1"></div>
        <div class="title-container">
            <div class="title">{title}</div>
            <div class="divider"></div>
            {"<div class='subtitle'>" + subtitle + "</div>" if subtitle else ""}
        </div>
        {"<div class='footnote'>" + footnote + "</div>" if footnote else ""}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# BULLET LIST — Staggered cards with left accent
# ══════════════════════════════════════════════════════════════════════════════

def bullet_list_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    items = data["items"]
    callout = data.get("callout", "")

    items_html = ""
    for i, item in enumerate(items):
        delay = 0.7 + i * 0.25
        color = c["palette"][i % len(c["palette"])]
        items_html += f"""
        <div class="bullet-card anim-item"
             style="animation-name: slideInLeft; animation-delay: {delay:.2f}s">
            <div class="bullet-accent" style="background: linear-gradient(180deg, {color}, {_hex_to_rgba(color, 0.3)})"></div>
            <div class="bullet-num" style="color: {color}">{i+1:02d}</div>
            <div class="bullet-text">{_esc(item)}</div>
        </div>"""

    callout_delay = 0.7 + len(items) * 0.25 + 0.4
    callout_html = ""
    if callout:
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: {callout_delay:.2f}s">
            <div class="callout-icon">!</div>
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    css = f"""
    .scene {{ background: linear-gradient(175deg, {c['bg']} 0%, #f0f4f8 100%);
              padding: 100px 60px; }}
    .bg-dots {{ opacity: 0.5; }}
    .header {{ font-size: 52px; font-weight: 800; color: {c['text_dark']};
               letter-spacing: -0.5px; line-height: 1.2;
               opacity: 0; animation: fadeInUp 0.6s 0.2s forwards; }}
    .header-accent {{ height: 4px; width: 60px; border-radius: 2px; margin: 20px 0 50px;
        background: linear-gradient(90deg, {c['blue']}, {c['green']});
        transform-origin: left; opacity: 0;
        animation: expandLine 0.5s 0.5s forwards; }}
    .bullet-card {{ display: flex; align-items: flex-start; gap: 20px;
                    background: {c['bg_card']}; border-radius: 16px;
                    padding: 28px 28px 28px 0; margin-bottom: 20px;
                    box-shadow: 0 2px 20px rgba(0,0,0,0.04), 0 1px 4px rgba(0,0,0,0.06);
                    overflow: hidden; position: relative; }}
    .bullet-accent {{ width: 5px; min-height: 100%; border-radius: 0 3px 3px 0;
                      flex-shrink: 0; align-self: stretch; }}
    .bullet-num {{ font-size: 28px; font-weight: 800; font-family: 'JetBrains Mono', monospace;
                   flex-shrink: 0; margin-left: 16px; margin-top: 2px; }}
    .bullet-text {{ font-size: 34px; color: {c['text_body']}; line-height: 1.45;
                    font-weight: 500; }}
    .callout-box {{ position: absolute; bottom: 90px; left: 50px; right: 50px;
                    display: flex; align-items: center; gap: 20px;
                    background: linear-gradient(135deg, {_hex_to_rgba(c['orange'], 0.08)}, {_hex_to_rgba(c['orange'], 0.03)});
                    border: 1.5px solid {_hex_to_rgba(c['orange'], 0.25)};
                    border-radius: 16px; padding: 28px 32px; }}
    .callout-icon {{ width: 44px; height: 44px; border-radius: 12px; flex-shrink: 0;
                     background: {c['orange']}; color: white; font-size: 24px; font-weight: 800;
                     display: flex; align-items: center; justify-content: center; }}
    .callout-text {{ font-size: 30px; color: {c['text_dark']}; font-weight: 600; line-height: 1.4; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="header">{header}</div>
        <div class="header-accent"></div>
        {items_html}
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# FLOWCHART — Vertical numbered pipeline
# ══════════════════════════════════════════════════════════════════════════════

def flowchart_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    stages = data["stages"]
    callout = data.get("callout", "")

    stages_html = ""
    for i, stage in enumerate(stages):
        delay = 0.5 + i * 0.35
        label = _esc(stage["label"].replace("\n", " "))
        color = c["palette"][i % len(c["palette"])]
        bg_fade = _hex_to_rgba(color, 0.06)

        stages_html += f"""
        <div class="flow-node anim-item"
             style="animation-name: scaleIn; animation-delay: {delay:.2f}s">
            <div class="node-badge" style="background: {color}">{i+1}</div>
            <div class="node-card" style="border-color: {_hex_to_rgba(color, 0.3)}; background: linear-gradient(135deg, {c['bg_card']}, {bg_fade})">
                <div class="node-label">{label}</div>
            </div>
        </div>"""

        if i < len(stages) - 1:
            ad = delay + 0.2
            stages_html += f"""
            <div class="connector anim-item"
                 style="animation-name: growHeight; animation-delay: {ad:.2f}s; animation-duration: 0.4s">
                <div class="connector-line" style="background: linear-gradient(180deg, {color}, {c['palette'][(i+1) % len(c['palette'])]})"></div>
                <div class="connector-arrow" style="border-top-color: {c['palette'][(i+1) % len(c['palette'])]}"></div>
            </div>"""

    callout_delay = 0.5 + len(stages) * 0.35 + 0.5
    callout_html = ""
    if callout:
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: {callout_delay:.2f}s">
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    css = f"""
    .scene {{ background: linear-gradient(175deg, {c['bg']} 0%, #f0f4f8 100%);
              padding: 90px 60px; align-items: center; }}
    .header {{ font-size: 52px; font-weight: 800; color: {c['text_dark']};
               text-align: center; letter-spacing: -0.5px;
               opacity: 0; animation: fadeInUp 0.6s 0.15s forwards; }}
    .header-line {{ width: 60px; height: 4px; border-radius: 2px; margin: 20px auto 40px;
        background: linear-gradient(90deg, {c['blue']}, {c['green']});
        opacity: 0; animation: scaleIn 0.4s 0.4s forwards; }}
    .flow-container {{ display: flex; flex-direction: column; align-items: center; width: 100%; }}
    .flow-node {{ width: 100%; position: relative; }}
    .node-badge {{ position: absolute; left: 20px; top: 50%; transform: translateY(-50%);
                   width: 48px; height: 48px; border-radius: 50%; color: white;
                   font-size: 22px; font-weight: 800; z-index: 2;
                   display: flex; align-items: center; justify-content: center;
                   box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
    .node-card {{ margin-left: 84px; border-radius: 16px; padding: 30px 32px;
                  border: 1.5px solid; box-shadow: 0 2px 16px rgba(0,0,0,0.04); }}
    .node-label {{ font-size: 36px; font-weight: 600; color: {c['text_dark']}; }}
    .connector {{ height: 40px; display: flex; flex-direction: column; align-items: center;
                  margin-left: 44px; overflow: hidden; }}
    .connector-line {{ width: 3px; flex: 1; border-radius: 2px; }}
    .connector-arrow {{ width: 0; height: 0; border-left: 8px solid transparent;
                        border-right: 8px solid transparent; border-top: 10px solid; }}
    .callout-box {{ position: absolute; bottom: 90px; left: 50px; right: 50px;
                    background: linear-gradient(135deg, {_hex_to_rgba(c['green'], 0.08)}, {_hex_to_rgba(c['green'], 0.03)});
                    border: 1.5px solid {_hex_to_rgba(c['green'], 0.25)};
                    border-radius: 16px; padding: 28px 32px; }}
    .callout-text {{ font-size: 30px; color: {c['text_dark']}; font-weight: 600;
                     line-height: 1.4; text-align: center; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="header">{header}</div>
        <div class="header-line"></div>
        <div class="flow-container">{stages_html}</div>
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# BAR CHART — Horizontal bars with animated fill
# ══════════════════════════════════════════════════════════════════════════════

def bar_chart_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    bars = data["bars"]
    suffix = data.get("value_suffix", "")
    callout = data.get("callout", "")

    max_val = max(b["value"] for b in bars) if bars else 1
    bar_max_w = 620

    bars_html = ""
    for i, bar in enumerate(bars):
        delay = 0.6 + i * 0.3
        label = _esc(bar["label"].replace("\n", " "))
        pct = (bar["value"] / max_val) * bar_max_w
        color = c["palette"][i % len(c["palette"])]

        bars_html += f"""
        <div class="bar-row anim-item"
             style="animation-name: slideInLeft; animation-delay: {delay:.2f}s">
            <div class="bar-meta">
                <span class="bar-label">{label}</span>
                <span class="bar-value" style="color: {color}">{bar['value']}{_esc(suffix)}</span>
            </div>
            <div class="bar-track">
                <div class="bar-fill" style="background: linear-gradient(90deg, {color}, {_hex_to_rgba(color, 0.7)});
                     width: {pct:.0f}px; animation: growWidth 1s {delay+0.15:.2f}s both
                     cubic-bezier(0.22, 1, 0.36, 1)">
                    <div class="bar-shimmer"></div>
                </div>
            </div>
        </div>"""

    callout_delay = 0.6 + len(bars) * 0.3 + 0.5
    callout_html = ""
    if callout:
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: {callout_delay:.2f}s">
            <div class="callout-icon">i</div>
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    css = f"""
    .scene {{ background: linear-gradient(175deg, {c['bg']} 0%, #f0f4f8 100%);
              padding: 100px 60px; }}
    .header {{ font-size: 52px; font-weight: 800; color: {c['text_dark']};
               letter-spacing: -0.5px;
               opacity: 0; animation: fadeInUp 0.6s 0.2s forwards; }}
    .header-line {{ width: 60px; height: 4px; border-radius: 2px; margin: 20px 0 50px;
        background: linear-gradient(90deg, {c['blue']}, {c['orange']});
        transform-origin: left; opacity: 0;
        animation: expandLine 0.5s 0.4s forwards; }}
    .bar-row {{ margin-bottom: 36px; }}
    .bar-meta {{ display: flex; justify-content: space-between; align-items: baseline;
                 margin-bottom: 12px; }}
    .bar-label {{ font-size: 34px; font-weight: 600; color: {c['text_body']}; }}
    .bar-value {{ font-size: 40px; font-weight: 900; font-family: 'JetBrains Mono', monospace; }}
    .bar-track {{ background: {_hex_to_rgba(c['border'], 0.5)}; border-radius: 12px;
                  height: 48px; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 12px; position: relative; overflow: hidden; }}
    .bar-shimmer {{ position: absolute; inset: 0;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
        background-size: 200% 100%;
        animation: shimmer 2s 1.5s ease-in-out infinite; }}
    .callout-box {{ position: absolute; bottom: 90px; left: 50px; right: 50px;
                    display: flex; align-items: center; gap: 20px;
                    background: linear-gradient(135deg, {_hex_to_rgba(c['orange'], 0.08)}, {_hex_to_rgba(c['orange'], 0.03)});
                    border: 1.5px solid {_hex_to_rgba(c['orange'], 0.25)};
                    border-radius: 16px; padding: 28px 32px; }}
    .callout-icon {{ width: 44px; height: 44px; border-radius: 12px; flex-shrink: 0;
                     background: {c['blue']}; color: white; font-size: 22px; font-weight: 800;
                     font-style: italic; font-family: serif;
                     display: flex; align-items: center; justify-content: center; }}
    .callout-text {{ font-size: 30px; color: {c['text_dark']}; font-weight: 600; line-height: 1.4; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="header">{header}</div>
        <div class="header-line"></div>
        {bars_html}
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# TWO PANEL — Side-by-side comparison as stacked cards
# ══════════════════════════════════════════════════════════════════════════════

def two_panel_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    callout = data.get("callout", "")

    def panel(title, items, color, anim, delay_base):
        items_li = ""
        for j, item in enumerate(items):
            d = delay_base + 0.3 + j * 0.15
            items_li += f"""
            <li class="anim-item" style="animation-name: fadeIn; animation-delay: {d:.2f}s">
                <span class="item-dot" style="background: {color}"></span>
                {_esc(item)}
            </li>"""
        return f"""
        <div class="panel anim-item"
             style="animation-name: {anim}; animation-delay: {delay_base:.2f}s">
            <div class="panel-header" style="border-left: 5px solid {color}">
                <span style="color: {color}">{_esc(title)}</span>
            </div>
            <ul>{items_li}</ul>
        </div>"""

    left = panel(data["left_title"], data["left_items"], c["blue"], "slideInLeft", 0.6)
    right = panel(data["right_title"], data["right_items"], c["red"], "slideInRight", 0.9)

    callout_html = ""
    if callout:
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: 2.2s">
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    css = f"""
    .scene {{ background: linear-gradient(175deg, {c['bg']} 0%, #f0f4f8 100%);
              padding: 100px 50px; }}
    .header {{ font-size: 48px; font-weight: 800; color: {c['text_dark']};
               text-align: center; letter-spacing: -0.5px;
               opacity: 0; animation: fadeInUp 0.6s 0.2s forwards; }}
    .header-line {{ width: 60px; height: 4px; border-radius: 2px; margin: 20px auto 40px;
        background: linear-gradient(90deg, {c['blue']}, {c['red']});
        opacity: 0; animation: scaleIn 0.4s 0.4s forwards; }}
    .panels {{ display: flex; flex-direction: column; gap: 28px; }}
    .panel {{ background: {c['bg_card']}; border-radius: 20px; padding: 32px;
              box-shadow: 0 4px 24px rgba(0,0,0,0.06); }}
    .panel-header {{ font-size: 38px; font-weight: 700; padding-left: 20px; margin-bottom: 24px; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ font-size: 30px; color: {c['text_body']}; padding: 14px 0;
          display: flex; align-items: flex-start; gap: 14px; line-height: 1.4; }}
    .item-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-top: 10px; }}
    .callout-box {{ position: absolute; bottom: 90px; left: 50px; right: 50px;
                    background: linear-gradient(135deg, {_hex_to_rgba(c['green'], 0.08)}, {_hex_to_rgba(c['green'], 0.03)});
                    border: 1.5px solid {_hex_to_rgba(c['green'], 0.25)};
                    border-radius: 16px; padding: 28px 32px; text-align: center; }}
    .callout-text {{ font-size: 30px; color: {c['text_dark']}; font-weight: 600; line-height: 1.4; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="header">{header}</div>
        <div class="header-line"></div>
        <div class="panels">{left}{right}</div>
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# COMPARISON TABLE
# ══════════════════════════════════════════════════════════════════════════════

def comparison_table_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    columns = data["columns"]
    rows = data["rows"]
    callout = data.get("callout", "")

    th_cells = "".join(f"<th>{_esc(col)}</th>" for col in columns)
    tr_html = ""
    for i, row in enumerate(rows):
        delay = 0.7 + i * 0.2
        cells = "".join(f"<td>{_esc(cell)}</td>" for cell in row)
        tr_html += f"""<tr class="anim-item"
            style="animation-name: fadeIn; animation-delay: {delay:.2f}s">{cells}</tr>"""

    callout_html = ""
    if callout:
        cd = 0.7 + len(rows) * 0.2 + 0.4
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: {cd:.2f}s">
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    css = f"""
    .scene {{ background: linear-gradient(175deg, {c['bg']} 0%, #f0f4f8 100%);
              padding: 100px 45px; }}
    .header {{ font-size: 48px; font-weight: 800; color: {c['text_dark']};
               opacity: 0; animation: fadeInUp 0.6s 0.2s forwards; }}
    .header-line {{ width: 60px; height: 4px; border-radius: 2px; margin: 20px 0 40px;
        background: {c['blue']}; transform-origin: left; opacity: 0;
        animation: expandLine 0.4s 0.4s forwards; }}
    .table-wrap {{ border-radius: 20px; overflow: hidden;
                   box-shadow: 0 4px 24px rgba(0,0,0,0.06);
                   opacity: 0; animation: fadeIn 0.4s 0.5s forwards; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ background: linear-gradient(135deg, {c['blue']}, {_hex_to_rgba(c['blue'], 0.85)});
          color: white; font-size: 26px; font-weight: 700; padding: 22px 18px; text-align: left; }}
    td {{ background: {c['bg_card']}; font-size: 25px; color: {c['text_body']};
          padding: 18px 18px; border-bottom: 1px solid {c['border']}; font-weight: 500; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:nth-child(even) td {{ background: {_hex_to_rgba(c['blue'], 0.03)}; }}
    .callout-box {{ position: absolute; bottom: 90px; left: 45px; right: 45px;
                    background: {_hex_to_rgba(c['orange'], 0.06)};
                    border: 1.5px solid {_hex_to_rgba(c['orange'], 0.2)};
                    border-radius: 16px; padding: 24px 28px; text-align: center; }}
    .callout-text {{ font-size: 28px; color: {c['text_dark']}; font-weight: 600; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="header">{header}</div>
        <div class="header-line"></div>
        <div class="table-wrap"><table><thead><tr>{th_cells}</tr></thead><tbody>{tr_html}</tbody></table></div>
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# SCATTER PLOT — SVG with animated dots
# ══════════════════════════════════════════════════════════════════════════════

def scatter_plot_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    clusters = data["clusters"]
    axes = data.get("axes", ["X", "Y"])
    callout = data.get("callout", "")

    rng = random.Random(42)
    plot_w, plot_h = 920, 920
    m = 70

    dots_svg = ""
    legend_html = ""
    for ci, cluster in enumerate(clusters):
        cx, cy = cluster["center"]
        n = cluster.get("n", 20)
        spread = cluster.get("spread", 0.4)
        color = c["palette"][ci % len(c["palette"])]
        db = 0.6 + ci * 0.25

        for j in range(n):
            x = cx + rng.gauss(0, spread)
            y = cy + rng.gauss(0, spread)
            sx = m + (x + 4) / 8 * (plot_w - 2*m)
            sy = (plot_h - m) - (y + 4) / 8 * (plot_h - 2*m)
            d = db + j * 0.015
            dots_svg += (f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="9" fill="{color}" opacity="0">'
                        f'<animate attributeName="opacity" from="0" to="0.8" '
                        f'dur="0.25s" begin="{d:.2f}s" fill="freeze"/>'
                        f'<animate attributeName="r" from="0" to="9" '
                        f'dur="0.3s" begin="{d:.2f}s" fill="freeze"/></circle>\n')

        legend_html += f"""
        <div class="legend-item anim-item"
             style="animation-name: fadeIn; animation-delay: {db:.2f}s">
            <span class="ldot" style="background: {color}"></span>
            <span>{_esc(cluster['label'])}</span>
        </div>"""

    callout_html = ""
    if callout:
        cd = 0.6 + len(clusters) * 0.25 + 0.5
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: {cd:.2f}s">
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    css = f"""
    .scene {{ background: linear-gradient(175deg, {c['bg']} 0%, #f0f4f8 100%);
              padding: 80px 50px; align-items: center; }}
    .header {{ font-size: 48px; font-weight: 800; color: {c['text_dark']};
               text-align: center; opacity: 0; animation: fadeInUp 0.6s 0.15s forwards; }}
    .header-line {{ width: 60px; height: 4px; border-radius: 2px; margin: 16px auto 30px;
        background: {c['blue']}; opacity: 0; animation: scaleIn 0.4s 0.4s forwards; }}
    .plot-box {{ background: {c['bg_card']}; border-radius: 20px; padding: 20px;
                 box-shadow: 0 4px 24px rgba(0,0,0,0.06);
                 opacity: 0; animation: fadeIn 0.4s 0.4s forwards; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 16px 28px; justify-content: center; margin-top: 28px; }}
    .legend-item {{ display: flex; align-items: center; gap: 10px; font-size: 28px;
                    color: {c['text_body']}; font-weight: 600; }}
    .ldot {{ width: 18px; height: 18px; border-radius: 50%; }}
    .axis-label {{ font-size: 22px; fill: {c['text_muted']}; font-weight: 600; }}
    .callout-box {{ position: absolute; bottom: 80px; left: 50px; right: 50px;
                    background: {_hex_to_rgba(c['blue'], 0.06)};
                    border: 1.5px solid {_hex_to_rgba(c['blue'], 0.2)};
                    border-radius: 16px; padding: 24px 28px; text-align: center; }}
    .callout-text {{ font-size: 28px; color: {c['text_dark']}; font-weight: 600; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="header">{header}</div>
        <div class="header-line"></div>
        <div class="plot-box">
            <svg width="{plot_w}" height="{plot_h}" viewBox="0 0 {plot_w} {plot_h}">
                <line x1="{m}" y1="{plot_h-m}" x2="{plot_w-m}" y2="{plot_h-m}" stroke="{c['border']}" stroke-width="2"/>
                <line x1="{m}" y1="{m}" x2="{m}" y2="{plot_h-m}" stroke="{c['border']}" stroke-width="2"/>
                <text x="{plot_w/2}" y="{plot_h-20}" text-anchor="middle" class="axis-label">{_esc(axes[0])}</text>
                <text x="22" y="{plot_h/2}" text-anchor="middle" class="axis-label"
                      transform="rotate(-90, 22, {plot_h/2})">{_esc(axes[1])}</text>
                {dots_svg}
            </svg>
        </div>
        <div class="legend">{legend_html}</div>
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# EQUATION
# ══════════════════════════════════════════════════════════════════════════════

def equation_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    latex = data["latex"]
    explanation = data.get("explanation", "")
    callout = data.get("callout", "")

    css = f"""
    .scene {{ background: linear-gradient(175deg, {c['bg']} 0%, #f0f4f8 100%);
              padding: 100px 60px; justify-content: center; align-items: center; }}
    .eq-container {{ position: relative; z-index: 2; text-align: center; width: 100%; }}
    .header {{ font-size: 48px; font-weight: 800; color: {c['text_dark']};
               margin-bottom: 50px; opacity: 0; animation: fadeInUp 0.6s 0.2s forwards; }}
    .eq-box {{ background: {c['bg_card']}; border-radius: 24px; padding: 50px 36px;
               box-shadow: 0 8px 32px rgba(0,0,0,0.08);
               border: 1px solid {c['border']};
               opacity: 0; animation: scaleIn 0.7s 0.6s forwards; }}
    .eq-text {{ font-size: 38px; color: {c['text_dark']};
                font-family: 'JetBrains Mono', monospace; line-height: 1.6;
                word-break: break-all; }}
    .explanation {{ font-size: 32px; color: {c['text_body']}; line-height: 1.5;
                    margin-top: 44px; opacity: 0; animation: fadeIn 0.6s 1.2s forwards; }}
    .callout-box {{ position: absolute; bottom: 100px; left: 60px; right: 60px;
                    background: {_hex_to_rgba(c['blue'], 0.06)};
                    border: 1.5px solid {_hex_to_rgba(c['blue'], 0.2)};
                    border-radius: 16px; padding: 28px 32px; text-align: center;
                    opacity: 0; animation: fadeInUp 0.5s 1.6s forwards; }}
    .callout-text {{ font-size: 30px; color: {c['text_dark']}; font-weight: 600; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="gradient-orb orb1" style="width:400px;height:400px;top:200px;right:-80px;
             background:{_hex_to_rgba(c['blue'], 0.06)}"></div>
        <div class="eq-container">
            <div class="header">{header}</div>
            <div class="eq-box">
                <div class="eq-text">{_esc(latex)}</div>
            </div>
            {"<div class='explanation'>" + _esc(explanation) + "</div>" if explanation else ""}
        </div>
        {"<div class='callout-box'><div class='callout-text'>" + _esc(callout) + "</div></div>" if callout else ""}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════

def pipeline_diagram_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    left = data["left_track"]
    right = data["right_track"]
    center = data["center_block"]
    callout = data.get("callout", "")

    center_items = ""
    for i, item in enumerate(center.get("items", [])[:5]):
        d = 1.3 + i * 0.18
        center_items += f"""
        <div class="ci anim-item" style="animation-name: fadeIn; animation-delay: {d:.2f}s">
            <span class="ci-num">{i+1}</span> {_esc(item)}
        </div>"""

    callout_html = ""
    if callout:
        callout_html = f"""
        <div class="callout-box anim-item" style="animation-name: fadeInUp; animation-delay: 2.2s">
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    css = f"""
    .scene {{ background: linear-gradient(175deg, {c['bg']} 0%, #f0f4f8 100%);
              padding: 80px 50px; }}
    .header {{ font-size: 48px; font-weight: 800; color: {c['text_dark']};
               text-align: center; opacity: 0; animation: fadeInUp 0.6s 0.15s forwards; }}
    .header-line {{ width: 60px; height: 4px; margin: 16px auto 36px;
        background: {c['blue']}; border-radius: 2px;
        opacity: 0; animation: scaleIn 0.4s 0.4s forwards; }}
    .pipe {{ display: flex; flex-direction: column; align-items: center; gap: 16px; }}
    .side {{ width: 90%; border-radius: 20px; padding: 28px 32px; text-align: center;
             background: {c['bg_card']}; box-shadow: 0 4px 20px rgba(0,0,0,0.05); }}
    .side-title {{ font-size: 34px; font-weight: 700; }}
    .side-sub {{ font-size: 24px; color: {c['text_muted']}; margin-top: 6px; }}
    .arrow {{ font-size: 32px; color: {c['text_muted']}; }}
    .center {{ width: 90%; border-radius: 20px; padding: 32px;
               background: {c['bg_card']}; border: 2.5px solid {c['orange']};
               box-shadow: 0 8px 32px rgba(0,0,0,0.08); }}
    .center-title {{ font-size: 36px; font-weight: 800; color: {c['orange']};
                     text-align: center; margin-bottom: 20px; }}
    .ci {{ font-size: 27px; color: {c['text_body']}; padding: 10px 0;
           border-bottom: 1px solid {c['border']}; display: flex; gap: 12px; align-items: center; }}
    .ci:last-child {{ border-bottom: none; }}
    .ci-num {{ width: 28px; height: 28px; border-radius: 50%; background: {_hex_to_rgba(c['orange'], 0.15)};
               color: {c['orange']}; font-size: 16px; font-weight: 700; flex-shrink: 0;
               display: flex; align-items: center; justify-content: center; }}
    .callout-box {{ position: absolute; bottom: 80px; left: 50px; right: 50px;
                    background: {_hex_to_rgba(c['green'], 0.06)};
                    border: 1.5px solid {_hex_to_rgba(c['green'], 0.2)};
                    border-radius: 16px; padding: 24px 28px; text-align: center; }}
    .callout-text {{ font-size: 28px; color: {c['text_dark']}; font-weight: 600; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="header">{header}</div>
        <div class="header-line"></div>
        <div class="pipe">
            <div class="side anim-item" style="animation-name: slideInLeft; animation-delay: 0.5s;
                 border-top: 4px solid {c['blue']}">
                <div class="side-title" style="color: {c['blue']}">{_esc(left['label'])}</div>
                {"<div class='side-sub'>" + _esc(left.get('sublabel','')) + "</div>" if left.get('sublabel') else ""}
            </div>
            <div class="arrow anim-item" style="animation-name: fadeIn; animation-delay: 0.7s">▼</div>
            <div class="center anim-item" style="animation-name: scaleIn; animation-delay: 0.9s">
                <div class="center-title">{_esc(center['label'])}</div>
                {center_items}
            </div>
            <div class="arrow anim-item" style="animation-name: fadeIn; animation-delay: 0.7s">▲</div>
            <div class="side anim-item" style="animation-name: slideInRight; animation-delay: 0.5s;
                 border-top: 4px solid {c['green']}">
                <div class="side-title" style="color: {c['green']}">{_esc(right['label'])}</div>
                {"<div class='side-sub'>" + _esc(right.get('sublabel','')) + "</div>" if right.get('sublabel') else ""}
            </div>
        </div>
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# CLOSING — Dark, cinematic end card
# ══════════════════════════════════════════════════════════════════════════════

def closing_scene(data: dict, theme: dict) -> str:
    c = _tc(theme)
    title = _esc(data.get("title", "Key References"))
    refs = data.get("references", [])

    refs_html = ""
    for i, ref in enumerate(refs):
        delay = 0.9 + i * 0.2
        refs_html += f"""
        <div class="ref anim-item" style="animation-name: fadeIn; animation-delay: {delay:.2f}s">
            <span class="ref-num">{i+1}</span> {_esc(ref)}
        </div>"""

    cta_delay = 0.9 + len(refs) * 0.2 + 0.5

    css = f"""
    .scene {{ background: linear-gradient(160deg, #080818 0%, {c['bg_dark']} 40%, #0d1b2a 100%);
              justify-content: center; align-items: center; padding: 80px; }}
    .close-container {{ position: relative; z-index: 2; text-align: center; width: 100%; }}
    .title {{ font-size: 52px; font-weight: 800; color: white; margin-bottom: 16px;
              opacity: 0; animation: fadeInUp 0.6s 0.2s forwards; }}
    .divider {{ width: 80px; height: 4px; border-radius: 2px; margin: 0 auto 44px;
        background: linear-gradient(90deg, {c['blue']}, {c['green']});
        opacity: 0; animation: scaleIn 0.4s 0.6s forwards; }}
    .refs {{ text-align: left; max-width: 800px; margin: 0 auto; }}
    .ref {{ font-size: 26px; color: rgba(255,255,255,0.6); margin-bottom: 16px;
            display: flex; gap: 14px; align-items: flex-start; line-height: 1.4; }}
    .ref-num {{ width: 30px; height: 30px; border-radius: 8px; flex-shrink: 0;
                background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.5);
                font-size: 16px; font-weight: 700;
                display: flex; align-items: center; justify-content: center; }}
    .cta {{ font-size: 36px; font-weight: 700; margin-top: 60px;
            background: linear-gradient(90deg, {c['blue']}, {c['cyan']});
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text;
            opacity: 0; animation: fadeInUp 0.6s {cta_delay:.2f}s forwards; }}
    .bottom-bar {{ position: absolute; bottom: 0; left: 0; right: 0; height: 6px;
        background: linear-gradient(90deg, {c['blue']}, {c['green']}, {c['orange']});
        opacity: 0; animation: fadeIn 0.8s {cta_delay + 0.3:.2f}s forwards; }}
    """

    body = f"""<div class="scene">
        <div class="bg-grid"></div>
        <div class="gradient-orb orb1" style="width:500px;height:500px;top:-50px;right:-100px;
             background:{_hex_to_rgba(c['blue'], 0.1)}"></div>
        <div class="gradient-orb orb2" style="width:350px;height:350px;bottom:150px;left:-80px;
             background:{_hex_to_rgba(c['green'], 0.08)};animation-delay:0.5s"></div>
        <div class="close-container">
            <div class="title">{title}</div>
            <div class="divider"></div>
            <div class="refs">{refs_html}</div>
            <div class="cta">Follow for more science!</div>
        </div>
        <div class="bottom-bar"></div>
    </div>"""

    return _wrap_page(body, css, c["bg_dark"])


# ── Dispatcher ────────────────────────────────────────────────────────────────

SCENE_RENDERERS = {
    "hook": hook_scene,
    "title": title_scene,
    "bullet_list": bullet_list_scene,
    "flowchart": flowchart_scene,
    "bar_chart": bar_chart_scene,
    "two_panel": two_panel_scene,
    "comparison_table": comparison_table_scene,
    "scatter_plot": scatter_plot_scene,
    "equation": equation_scene,
    "pipeline_diagram": pipeline_diagram_scene,
    "closing": closing_scene,
}


def render_scene_html(scene_data: dict, theme: dict) -> str:
    """Render a scene to a production-quality HTML string."""
    renderer = SCENE_RENDERERS.get(scene_data.get("type", ""))
    if renderer is None:
        return ""
    return renderer(scene_data, theme)
