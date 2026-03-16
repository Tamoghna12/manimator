"""Generate production-quality HTML pages for portrait video scenes.

Each function returns a self-contained HTML page with CSS animations
at 1080x1920 portrait resolution. Design targets: Kurzgesagt-level
polish with gradient backgrounds, glassmorphism, smooth easing,
animated accents, and proper mobile visual hierarchy.
"""

from __future__ import annotations

import html
import math
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from manimator.timing import SceneTiming

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
    animation: kenBurns 8s ease-in-out forwards;
}

/* ── Keyframes ── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(60px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
@keyframes scaleIn {
    from { opacity: 0; transform: scale(0.82); }
    to { opacity: 1; transform: scale(1); }
}
/* Spring overshoot — items pop into place with a bounce */
@keyframes popIn {
    0%   { opacity: 0; transform: scale(0.75) translateY(30px); }
    60%  { opacity: 1; transform: scale(1.04) translateY(-4px); }
    80%  { transform: scale(0.98) translateY(2px); }
    100% { opacity: 1; transform: scale(1) translateY(0); }
}
@keyframes slideInLeft {
    from { opacity: 0; transform: translateX(-90px); }
    to { opacity: 1; transform: translateX(0); }
}
@keyframes slideInRight {
    from { opacity: 0; transform: translateX(90px); }
    to { opacity: 1; transform: translateX(0); }
}
@keyframes slideInDown {
    from { opacity: 0; transform: translateY(-60px); }
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
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-10px); }
}
@keyframes expandLine {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
}
@keyframes rotateIn {
    from { opacity: 0; transform: rotate(-12deg) scale(0.88); }
    to { opacity: 1; transform: rotate(0) scale(1); }
}
@keyframes countUp {
    from { opacity: 0; transform: translateY(24px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes glowPulse {
    0%, 100% { box-shadow: 0 0 20px rgba(255,255,255,0.1); }
    50% { box-shadow: 0 0 50px rgba(255,255,255,0.25); }
}
@keyframes gradientShift {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes kenBurns {
    from { transform: scale(1.0); }
    to { transform: scale(1.03); }
}

.anim-item {
    opacity: 0;
    animation-fill-mode: forwards;
    animation-duration: 0.65s;
    animation-timing-function: cubic-bezier(0.22, 1, 0.36, 1);
}

/* ── Decorative elements ── */
.bg-grid {
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px);
    background-size: 60px 60px;
    pointer-events: none;
}

.bg-dots {
    position: absolute;
    inset: 0;
    background-image: radial-gradient(circle, rgba(0,0,0,0.05) 1px, transparent 1px);
    background-size: 36px 36px;
    pointer-events: none;
}

/* Subtle noise texture adds film-grain depth to flat areas */
.bg-noise {
    position: absolute;
    inset: 0;
    opacity: 0.025;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    background-size: 256px 256px;
    pointer-events: none;
    mix-blend-mode: overlay;
}

/* Vignette adds cinematic edge-darkening */
.vignette {
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 50% 50%, transparent 55%, rgba(0,0,0,0.18) 100%);
    pointer-events: none;
    z-index: 10;
}

.gradient-orb {
    position: absolute;
    border-radius: 50%;
    filter: blur(90px);
    pointer-events: none;
    opacity: 0;
    animation: fadeIn 1.8s 0.2s forwards;
}
"""


def _esc(text: str) -> str:
    return html.escape(str(text))


def _wrap_page(body_html: str, css: str, bg_color: str = "#FAFAFA",
               branding: dict | None = None) -> str:
    watermark_html = ""
    if branding:
        wm = branding.get("watermark_text") or branding.get("channel_name") or ""
        if wm:
            watermark_html = f'<div class="watermark">{_esc(wm)}</div>'
    watermark_css = """
.watermark {
    position: fixed; top: 40px; right: 40px; z-index: 100;
    font-size: 18px; font-weight: 700; letter-spacing: 1px;
    color: rgba(255,255,255,0.25); pointer-events: none;
    text-transform: uppercase;
}
""" if watermark_html else ""
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>
{_BASE_CSS}
{watermark_css}
body {{ background: {bg_color}; }}
{css}
</style>
</head>
<body>{watermark_html}{body_html}</body>
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

def hook_scene(data: dict, theme: dict, timing: SceneTiming | None = None,
               branding: dict | None = None) -> str:
    c = _tc(theme)
    words = data["hook_text"].split()
    subtitle = data.get("subtitle", "")
    accent_label = (branding or {}).get("accent_label") or "Watch This"

    char_spans = []
    char_idx = 0
    for w_i, w in enumerate(words):
        for ch in w:
            delay = 0.4 + char_idx * 0.04
            char_spans.append(
                f'<span class="anim-item hook-char" '
                f'style="animation-name: fadeInUp; animation-delay: {delay:.2f}s; '
                f'animation-duration: 0.3s">{_esc(ch)}</span>'
            )
            char_idx += 1
        if w_i < len(words) - 1:
            char_spans.append('<span class="hook-space">&nbsp;</span>')
    words_html = "".join(char_spans)
    sub_delay = 0.4 + char_idx * 0.04 + 0.4

    css = f"""
    .scene {{
        background: linear-gradient(160deg, #05050f 0%, {c['bg_dark']} 45%, #0a1628 100%);
        justify-content: center; align-items: center; padding: 80px;
    }}
    .gradient-orb.orb1 {{ width: 700px; height: 700px; top: -150px; right: -180px;
        background: radial-gradient(circle, {_hex_to_rgba(c['blue'], 0.2)}, transparent 70%); }}
    .gradient-orb.orb2 {{ width: 500px; height: 500px; bottom: 150px; left: -120px;
        background: radial-gradient(circle, {_hex_to_rgba(c['purple'], 0.16)}, transparent 70%);
        animation-delay: 0.6s; }}
    .gradient-orb.orb3 {{ width: 300px; height: 300px; bottom: 600px; right: 50px;
        background: radial-gradient(circle, {_hex_to_rgba(c['cyan'], 0.1)}, transparent 70%);
        animation-delay: 0.9s; }}
    .hook-container {{ position: relative; z-index: 2; text-align: center; }}
    .accent-pill {{ display: inline-flex; align-items: center; gap: 10px;
        background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
        border-radius: 999px; padding: 10px 28px; margin-bottom: 50px;
        opacity: 0; animation: fadeIn 0.5s 0.1s forwards; }}
    .accent-dot {{ width: 8px; height: 8px; border-radius: 50%;
        background: {c['cyan']}; animation: pulse 2s 0.8s infinite; }}
    .accent-label {{ font-size: 22px; font-weight: 600; letter-spacing: 3px;
        text-transform: uppercase; color: rgba(255,255,255,0.5); }}
    .hook-text {{ font-size: 80px; font-weight: 900; line-height: 1.15; letter-spacing: -2px;
        display: flex; flex-wrap: wrap; justify-content: center; gap: 0; }}
    .hook-char {{ display: inline-block;
        background: linear-gradient(135deg, #ffffff 0%, {c['cyan']} 50%, {c['blue']} 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text;
        filter: drop-shadow(0 2px 24px {_hex_to_rgba(c['blue'], 0.4)}); }}
    .hook-space {{ display: inline-block; width: 18px; }}
    .hook-subtitle {{ font-size: 34px; font-weight: 500; letter-spacing: 1.5px;
        margin-top: 50px; color: rgba(255,255,255,0.55);
        opacity: 0; animation: fadeInUp 0.7s {sub_delay:.2f}s forwards; }}
    .bottom-accent {{ position: absolute; bottom: 0; left: 0; right: 0; height: 5px;
        background: linear-gradient(90deg, {c['blue']}, {c['cyan']}, {c['green']}, {c['orange']});
        background-size: 300% 100%;
        animation: gradientShift 4s linear infinite,
                   fadeIn 0.8s {sub_delay + 0.2:.2f}s both; }}
    """

    body = f"""<div class="scene">
        <div class="bg-grid"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
        <div class="gradient-orb orb1"></div>
        <div class="gradient-orb orb2"></div>
        <div class="gradient-orb orb3"></div>
        <div class="hook-container">
            <div class="accent-pill">
                <div class="accent-dot"></div>
                <span class="accent-label">{_esc(accent_label)}</span>
            </div>
            <div class="hook-text">{words_html}</div>
            {"<div class='hook-subtitle'>" + _esc(subtitle) + "</div>" if subtitle else ""}
        </div>
        <div class="bottom-accent"></div>
    </div>"""

    return _wrap_page(body, css, c["bg_dark"], branding=branding)


# ══════════════════════════════════════════════════════════════════════════════
# TITLE SCENE
# ══════════════════════════════════════════════════════════════════════════════

def title_scene(data: dict, theme: dict, timing: SceneTiming | None = None) -> str:
    c = _tc(theme)
    title = _esc(data["title"])
    subtitle = _esc(data.get("subtitle", ""))
    footnote = _esc(data.get("footnote", ""))

    css = f"""
    .scene {{ background: linear-gradient(160deg, {c['bg']} 0%, #e8eef5 55%, #f0f4f8 100%);
              justify-content: center; align-items: center; padding: 80px; }}
    .gradient-orb.orb1 {{ width: 700px; height: 700px; top: 50px; left: -150px;
        background: radial-gradient(circle, {_hex_to_rgba(c['blue'], 0.09)}, transparent 70%); }}
    .gradient-orb.orb2 {{ width: 450px; height: 450px; bottom: 200px; right: -100px;
        background: radial-gradient(circle, {_hex_to_rgba(c['green'], 0.07)}, transparent 70%);
        animation-delay: 0.4s; }}
    .title-container {{ position: relative; z-index: 2; text-align: center; }}
    .title {{ font-size: 70px; font-weight: 900; color: {c['text_dark']};
              line-height: 1.15; letter-spacing: -2px;
              opacity: 0; animation: fadeInUp 0.8s 0.3s forwards; }}
    .divider {{ width: 120px; height: 5px; border-radius: 3px; margin: 44px auto;
        background: linear-gradient(90deg, {c['blue']}, {c['green']});
        transform-origin: center; opacity: 0;
        animation: scaleIn 0.5s 0.85s forwards; }}
    .subtitle {{ font-size: 36px; color: {c['text_body']}; font-weight: 400;
                 line-height: 1.55; opacity: 0; animation: fadeIn 0.7s 1.1s forwards; }}
    .footnote {{ font-size: 24px; color: {c['text_muted']}; position: absolute;
                 bottom: 140px; left: 80px; right: 80px; text-align: center;
                 opacity: 0; animation: fadeIn 0.5s 1.6s forwards; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
        <div class="gradient-orb orb1"></div>
        <div class="gradient-orb orb2"></div>
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

def bullet_list_scene(data: dict, theme: dict, timing: SceneTiming | None = None) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    items = data["items"]
    callout = data.get("callout", "")

    items_html = ""
    for i, item in enumerate(items):
        # timing.element_delays: [header, item_0, item_1, ..., callout]
        delay = timing.element_delays[i + 1] if timing and timing.element_delays and i + 1 < len(timing.element_delays) else 0.7 + i * 0.25
        color = c["palette"][i % len(c["palette"])]
        anim = "slideInLeft" if i % 2 == 0 else "slideInRight"
        items_html += f"""
        <div class="bullet-card anim-item"
             style="animation-name: {anim}; animation-delay: {delay:.2f}s">
            <div class="bullet-accent" style="background: linear-gradient(180deg, {color}, {_hex_to_rgba(color, 0.3)})"></div>
            <div class="bullet-num" style="color: {color}">{i+1:02d}</div>
            <div class="bullet-text">{_esc(item)}</div>
        </div>"""

    callout_delay = (timing.element_delays[-1] if timing and timing.element_delays else 0.7 + len(items) * 0.25 + 0.4)
    callout_html = ""
    if callout:
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: {callout_delay:.2f}s">
            <div class="callout-icon">!</div>
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    header_delay = timing.header_delay if timing else 0.2
    css = f"""
    .scene {{ background: linear-gradient(160deg, {c['bg']} 0%, #e9eff6 50%, #f2f5f8 100%);
              padding: 100px 60px; }}
    .bg-dots {{ opacity: 0.4; }}
    .header {{ font-size: 54px; font-weight: 900; color: {c['text_dark']};
               letter-spacing: -1px; line-height: 1.2;
               opacity: 0; animation: fadeInUp 0.65s {header_delay:.2f}s forwards; }}
    .header-accent {{ height: 5px; width: 70px; border-radius: 3px; margin: 22px 0 48px;
        background: linear-gradient(90deg, {c['blue']}, {c['green']});
        transform-origin: left; opacity: 0;
        animation: expandLine 0.5s 0.5s forwards; }}
    .bullet-card {{ display: flex; align-items: flex-start; gap: 20px;
                    background: {c['bg_card']}; border-radius: 20px;
                    padding: 30px 30px 30px 0; margin-bottom: 22px;
                    box-shadow:
                        0 1px 2px rgba(0,0,0,0.04),
                        0 4px 16px rgba(0,0,0,0.06),
                        0 12px 32px rgba(0,0,0,0.04);
                    overflow: hidden; position: relative; }}
    .bullet-accent {{ width: 6px; min-height: 100%; border-radius: 0 4px 4px 0;
                      flex-shrink: 0; align-self: stretch; }}
    .bullet-num {{ font-size: 28px; font-weight: 900; font-family: 'JetBrains Mono', monospace;
                   flex-shrink: 0; margin-left: 16px; margin-top: 2px; opacity: 0.8; }}
    .bullet-text {{ font-size: 35px; color: {c['text_body']}; line-height: 1.45;
                    font-weight: 500; }}
    .callout-box {{ position: absolute; bottom: 90px; left: 50px; right: 50px;
                    display: flex; align-items: center; gap: 20px;
                    background: linear-gradient(135deg, {_hex_to_rgba(c['orange'], 0.1)}, {_hex_to_rgba(c['orange'], 0.04)});
                    border: 1.5px solid {_hex_to_rgba(c['orange'], 0.3)};
                    border-radius: 18px; padding: 30px 34px;
                    box-shadow: 0 4px 20px {_hex_to_rgba(c['orange'], 0.1)}; }}
    .callout-icon {{ width: 46px; height: 46px; border-radius: 14px; flex-shrink: 0;
                     background: {c['orange']}; color: white; font-size: 24px; font-weight: 800;
                     display: flex; align-items: center; justify-content: center;
                     box-shadow: 0 4px 12px {_hex_to_rgba(c['orange'], 0.4)}; }}
    .callout-text {{ font-size: 30px; color: {c['text_dark']}; font-weight: 600; line-height: 1.4; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
        <div class="header">{header}</div>
        <div class="header-accent"></div>
        {items_html}
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# FLOWCHART — Vertical numbered pipeline
# ══════════════════════════════════════════════════════════════════════════════

def flowchart_scene(data: dict, theme: dict, timing: SceneTiming | None = None) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    stages = data["stages"]
    callout = data.get("callout", "")

    stages_html = ""
    for i, stage in enumerate(stages):
        delay = timing.element_delays[i + 1] if timing and timing.element_delays and i + 1 < len(timing.element_delays) else 0.5 + i * 0.35
        label = _esc(stage["label"].replace("\n", " "))
        color = c["palette"][i % len(c["palette"])]
        bg_fade = _hex_to_rgba(color, 0.06)

        stages_html += f"""
        <div class="flow-node anim-item"
             style="animation-name: popIn; animation-delay: {delay:.2f}s">
            <div class="node-badge" style="background: {color}">{i+1}</div>
            <div class="node-card" style="border-color: {_hex_to_rgba(color, 0.3)}; background: linear-gradient(135deg, {c['bg_card']}, {bg_fade})">
                <div class="node-label">{label}</div>
            </div>
        </div>"""

        if i < len(stages) - 1:
            ad = delay + 0.2
            next_color = c['palette'][(i+1) % len(c['palette'])]
            stages_html += f"""
            <div class="connector anim-item"
                 style="animation-name: fadeIn; animation-delay: {ad:.2f}s; animation-duration: 0.3s">
                <svg width="60" height="42" viewBox="0 0 60 42" style="display:block;margin:0 auto">
                    <defs>
                        <linearGradient id="cg{i}" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stop-color="{color}"/>
                            <stop offset="100%" stop-color="{next_color}"/>
                        </linearGradient>
                    </defs>
                    <line x1="30" y1="0" x2="30" y2="32" stroke="url(#cg{i})" stroke-width="3"
                          stroke-dasharray="32" stroke-dashoffset="32" stroke-linecap="round">
                        <animate attributeName="stroke-dashoffset" from="32" to="0"
                                 dur="0.4s" begin="{ad:.2f}s" fill="freeze"/>
                    </line>
                    <polygon points="22,30 30,42 38,30" fill="{next_color}" opacity="0">
                        <animate attributeName="opacity" from="0" to="1"
                                 dur="0.2s" begin="{ad+0.3:.2f}s" fill="freeze"/>
                    </polygon>
                </svg>
            </div>"""

    callout_delay = (timing.element_delays[-1] if timing and timing.element_delays else 0.5 + len(stages) * 0.35 + 0.5)
    callout_html = ""
    if callout:
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: {callout_delay:.2f}s">
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    header_delay = timing.header_delay if timing else 0.15
    css = f"""
    .scene {{ background: linear-gradient(160deg, {c['bg']} 0%, #e9eff6 50%, #f2f5f8 100%);
              padding: 90px 60px; align-items: center; }}
    .header {{ font-size: 54px; font-weight: 900; color: {c['text_dark']};
               text-align: center; letter-spacing: -1px;
               opacity: 0; animation: fadeInUp 0.65s {header_delay:.2f}s forwards; }}
    .header-line {{ width: 70px; height: 5px; border-radius: 3px; margin: 22px auto 40px;
        background: linear-gradient(90deg, {c['blue']}, {c['green']});
        opacity: 0; animation: scaleIn 0.4s 0.4s forwards; }}
    .flow-container {{ display: flex; flex-direction: column; align-items: center; width: 100%; }}
    .flow-node {{ width: 100%; position: relative; }}
    .node-badge {{ position: absolute; left: 20px; top: 50%; transform: translateY(-50%);
                   width: 52px; height: 52px; border-radius: 50%; color: white;
                   font-size: 24px; font-weight: 900; z-index: 2;
                   display: flex; align-items: center; justify-content: center;
                   box-shadow: 0 4px 20px rgba(0,0,0,0.2); }}
    .node-card {{ margin-left: 88px; border-radius: 18px; padding: 30px 32px;
                  border: 1.5px solid;
                  box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.06); }}
    .node-label {{ font-size: 36px; font-weight: 600; color: {c['text_dark']}; }}
    .connector {{ height: 42px; display: flex; align-items: center; justify-content: center;
                  margin-left: 44px; }}
    .callout-box {{ position: absolute; bottom: 90px; left: 50px; right: 50px;
                    background: linear-gradient(135deg, {_hex_to_rgba(c['green'], 0.1)}, {_hex_to_rgba(c['green'], 0.04)});
                    border: 1.5px solid {_hex_to_rgba(c['green'], 0.3)};
                    border-radius: 18px; padding: 30px 34px;
                    box-shadow: 0 4px 20px {_hex_to_rgba(c['green'], 0.1)}; }}
    .callout-text {{ font-size: 30px; color: {c['text_dark']}; font-weight: 600;
                     line-height: 1.4; text-align: center; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
        <div class="header">{header}</div>
        <div class="header-line"></div>
        <div class="flow-container">{stages_html}</div>
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# BAR CHART — Horizontal bars with animated fill
# ══════════════════════════════════════════════════════════════════════════════

def bar_chart_scene(data: dict, theme: dict, timing: SceneTiming | None = None) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    bars = data["bars"]
    suffix = data.get("value_suffix", "")
    callout = data.get("callout", "")

    max_val = max(b["value"] for b in bars) if bars else 1
    bar_max_w = 620

    bars_html = ""
    for i, bar in enumerate(bars):
        delay = timing.element_delays[i + 1] if timing and timing.element_delays and i + 1 < len(timing.element_delays) else 0.6 + i * 0.3
        label = _esc(bar["label"].replace("\n", " "))
        pct = (bar["value"] / max_val) * bar_max_w
        color = c["palette"][i % len(c["palette"])]

        bars_html += f"""
        <div class="bar-row anim-item"
             style="animation-name: slideInLeft; animation-delay: {delay:.2f}s">
            <div class="bar-meta">
                <span class="bar-label">{label}</span>
                <span class="bar-value anim-item" style="color: {color}; animation-name: countUp; animation-delay: {delay+0.3:.2f}s; animation-duration: 0.6s">{bar['value']}{_esc(suffix)}</span>
            </div>
            <div class="bar-track">
                <div class="bar-fill" style="background: linear-gradient(90deg, {color}, {_hex_to_rgba(color, 0.7)});
                     width: {pct:.0f}px; animation: growWidth 1s {delay+0.15:.2f}s both
                     cubic-bezier(0.22, 1, 0.36, 1)">
                    <div class="bar-shimmer"></div>
                </div>
            </div>
        </div>"""

    callout_delay = (timing.element_delays[-1] if timing and timing.element_delays else 0.6 + len(bars) * 0.3 + 0.5)
    callout_html = ""
    if callout:
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: {callout_delay:.2f}s">
            <div class="callout-icon">i</div>
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    header_delay = timing.header_delay if timing else 0.2
    css = f"""
    .scene {{ background: linear-gradient(160deg, {c['bg']} 0%, #e9eff6 50%, #f2f5f8 100%);
              padding: 100px 60px; }}
    .header {{ font-size: 54px; font-weight: 900; color: {c['text_dark']};
               letter-spacing: -1px;
               opacity: 0; animation: fadeInUp 0.65s {header_delay:.2f}s forwards; }}
    .header-line {{ width: 70px; height: 5px; border-radius: 3px; margin: 22px 0 50px;
        background: linear-gradient(90deg, {c['blue']}, {c['orange']});
        transform-origin: left; opacity: 0;
        animation: expandLine 0.5s 0.4s forwards; }}
    .bar-row {{ margin-bottom: 38px; }}
    .bar-meta {{ display: flex; justify-content: space-between; align-items: baseline;
                 margin-bottom: 14px; }}
    .bar-label {{ font-size: 34px; font-weight: 600; color: {c['text_body']}; }}
    .bar-value {{ font-size: 42px; font-weight: 900; font-family: 'JetBrains Mono', monospace; }}
    .bar-track {{ background: rgba(0,0,0,0.06); border-radius: 14px;
                  height: 52px; overflow: hidden;
                  box-shadow: inset 0 2px 6px rgba(0,0,0,0.08); }}
    .bar-fill {{ height: 100%; border-radius: 14px; position: relative; overflow: hidden;
                 box-shadow: 0 4px 16px rgba(0,0,0,0.15); }}
    .bar-shimmer {{ position: absolute; inset: 0;
        background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.25) 50%, transparent 100%);
        background-size: 200% 100%;
        animation: shimmer 2.5s 1.2s ease-in-out infinite; }}
    .callout-box {{ position: absolute; bottom: 90px; left: 50px; right: 50px;
                    display: flex; align-items: center; gap: 20px;
                    background: linear-gradient(135deg, {_hex_to_rgba(c['orange'], 0.1)}, {_hex_to_rgba(c['orange'], 0.04)});
                    border: 1.5px solid {_hex_to_rgba(c['orange'], 0.3)};
                    border-radius: 18px; padding: 30px 34px;
                    box-shadow: 0 4px 20px {_hex_to_rgba(c['orange'], 0.1)}; }}
    .callout-icon {{ width: 46px; height: 46px; border-radius: 14px; flex-shrink: 0;
                     background: {c['blue']}; color: white; font-size: 22px; font-weight: 800;
                     font-style: italic; font-family: serif;
                     display: flex; align-items: center; justify-content: center;
                     box-shadow: 0 4px 12px {_hex_to_rgba(c['blue'], 0.4)}; }}
    .callout-text {{ font-size: 30px; color: {c['text_dark']}; font-weight: 600; line-height: 1.4; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
        <div class="header">{header}</div>
        <div class="header-line"></div>
        {bars_html}
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# TWO PANEL — Side-by-side comparison as stacked cards
# ══════════════════════════════════════════════════════════════════════════════

def two_panel_scene(data: dict, theme: dict, timing: SceneTiming | None = None) -> str:
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
    .scene {{ background: linear-gradient(160deg, {c['bg']} 0%, #e9eff6 50%, #f2f5f8 100%);
              padding: 100px 50px; }}
    .header {{ font-size: 50px; font-weight: 900; color: {c['text_dark']};
               text-align: center; letter-spacing: -1px;
               opacity: 0; animation: fadeInUp 0.65s 0.2s forwards; }}
    .header-line {{ width: 70px; height: 5px; border-radius: 3px; margin: 22px auto 40px;
        background: linear-gradient(90deg, {c['blue']}, {c['red']});
        opacity: 0; animation: scaleIn 0.4s 0.4s forwards; }}
    .panels {{ display: flex; flex-direction: column; gap: 28px; }}
    .panel {{ background: {c['bg_card']}; border-radius: 22px; padding: 34px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 8px 28px rgba(0,0,0,0.06); }}
    .panel-header {{ font-size: 38px; font-weight: 700; padding-left: 20px; margin-bottom: 24px; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ font-size: 30px; color: {c['text_body']}; padding: 14px 0;
          display: flex; align-items: flex-start; gap: 14px; line-height: 1.4; }}
    .item-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-top: 10px; }}
    .callout-box {{ position: absolute; bottom: 90px; left: 50px; right: 50px;
                    background: linear-gradient(135deg, {_hex_to_rgba(c['green'], 0.1)}, {_hex_to_rgba(c['green'], 0.04)});
                    border: 1.5px solid {_hex_to_rgba(c['green'], 0.3)};
                    border-radius: 18px; padding: 30px 34px; text-align: center;
                    box-shadow: 0 4px 20px {_hex_to_rgba(c['green'], 0.1)}; }}
    .callout-text {{ font-size: 30px; color: {c['text_dark']}; font-weight: 600; line-height: 1.4; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
        <div class="header">{header}</div>
        <div class="header-line"></div>
        <div class="panels">{left}{right}</div>
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# COMPARISON TABLE
# ══════════════════════════════════════════════════════════════════════════════

def comparison_table_scene(data: dict, theme: dict, timing: SceneTiming | None = None) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    columns = data["columns"]
    rows = data["rows"]
    callout = data.get("callout", "")

    th_cells = "".join(f"<th>{_esc(col)}</th>" for col in columns)
    tr_html = ""
    for i, row in enumerate(rows):
        delay = timing.element_delays[i + 1] if timing and timing.element_delays and i + 1 < len(timing.element_delays) else 0.7 + i * 0.2
        cells = "".join(f"<td>{_esc(cell)}</td>" for cell in row)
        tr_html += f"""<tr class="anim-item"
            style="animation-name: fadeIn; animation-delay: {delay:.2f}s">{cells}</tr>"""

    callout_html = ""
    if callout:
        cd = timing.element_delays[-1] if timing and timing.element_delays else 0.7 + len(rows) * 0.2 + 0.4
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: {cd:.2f}s">
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    header_delay = timing.header_delay if timing else 0.2
    css = f"""
    .scene {{ background: linear-gradient(160deg, {c['bg']} 0%, #e9eff6 50%, #f2f5f8 100%);
              padding: 100px 45px; }}
    .header {{ font-size: 50px; font-weight: 900; color: {c['text_dark']};
               letter-spacing: -1px;
               opacity: 0; animation: fadeInUp 0.65s {header_delay:.2f}s forwards; }}
    .header-line {{ width: 70px; height: 5px; border-radius: 3px; margin: 22px 0 40px;
        background: {c['blue']}; transform-origin: left; opacity: 0;
        animation: expandLine 0.4s 0.4s forwards; }}
    .table-wrap {{ border-radius: 22px; overflow: hidden;
                   box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 8px 28px rgba(0,0,0,0.07);
                   opacity: 0; animation: fadeIn 0.5s 0.5s forwards; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ background: linear-gradient(135deg, {c['blue']}, {_hex_to_rgba(c['blue'], 0.82)});
          color: white; font-size: 27px; font-weight: 700; padding: 24px 20px; text-align: left; }}
    td {{ background: {c['bg_card']}; font-size: 26px; color: {c['text_body']};
          padding: 20px 20px; border-bottom: 1px solid {c['border']}; font-weight: 500; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:nth-child(even) td {{ background: {_hex_to_rgba(c['blue'], 0.025)}; }}
    .callout-box {{ position: absolute; bottom: 90px; left: 45px; right: 45px;
                    background: {_hex_to_rgba(c['orange'], 0.08)};
                    border: 1.5px solid {_hex_to_rgba(c['orange'], 0.25)};
                    border-radius: 18px; padding: 26px 30px; text-align: center;
                    box-shadow: 0 4px 20px {_hex_to_rgba(c['orange'], 0.08)}; }}
    .callout-text {{ font-size: 28px; color: {c['text_dark']}; font-weight: 600; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
        <div class="header">{header}</div>
        <div class="header-line"></div>
        <div class="table-wrap"><table><thead><tr>{th_cells}</tr></thead><tbody>{tr_html}</tbody></table></div>
        {callout_html}
    </div>"""

    return _wrap_page(body, css, c["bg"])


# ══════════════════════════════════════════════════════════════════════════════
# SCATTER PLOT — SVG with animated dots
# ══════════════════════════════════════════════════════════════════════════════

def scatter_plot_scene(data: dict, theme: dict, timing: SceneTiming | None = None) -> str:
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
        db = timing.element_delays[ci + 1] if timing and timing.element_delays and ci + 1 < len(timing.element_delays) else 0.6 + ci * 0.25

        for j in range(n):
            x = cx + rng.gauss(0, spread)
            y = cy + rng.gauss(0, spread)
            sx = m + (x + 4) / 8 * (plot_w - 2*m)
            sy = (plot_h - m) - (y + 4) / 8 * (plot_h - 2*m)
            d = db + j * 0.015
            dots_svg += (f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="9" fill="{color}" opacity="0">'
                        f'<animate attributeName="opacity" from="0" to="0.85" '
                        f'dur="0.2s" begin="{d:.2f}s" fill="freeze"/>'
                        f'<animate attributeName="r" from="0" to="11" '
                        f'dur="0.15s" begin="{d:.2f}s" fill="freeze"/>'
                        f'<animate attributeName="r" from="11" to="9" '
                        f'dur="0.15s" begin="{d+0.15:.2f}s" fill="freeze"/></circle>\n')

        legend_html += f"""
        <div class="legend-item anim-item"
             style="animation-name: fadeIn; animation-delay: {db:.2f}s">
            <span class="ldot" style="background: {color}"></span>
            <span>{_esc(cluster['label'])}</span>
        </div>"""

    callout_html = ""
    if callout:
        cd = timing.element_delays[-1] if timing and timing.element_delays else 0.6 + len(clusters) * 0.25 + 0.5
        callout_html = f"""
        <div class="callout-box anim-item"
             style="animation-name: fadeInUp; animation-delay: {cd:.2f}s">
            <div class="callout-text">{_esc(callout)}</div>
        </div>"""

    header_delay = timing.header_delay if timing else 0.15
    css = f"""
    .scene {{ background: linear-gradient(160deg, {c['bg']} 0%, #e9eff6 50%, #f2f5f8 100%);
              padding: 80px 50px; align-items: center; }}
    .header {{ font-size: 50px; font-weight: 900; color: {c['text_dark']};
               text-align: center; letter-spacing: -1px;
               opacity: 0; animation: fadeInUp 0.65s {header_delay:.2f}s forwards; }}
    .header-line {{ width: 70px; height: 5px; border-radius: 3px; margin: 18px auto 30px;
        background: {c['blue']}; opacity: 0; animation: scaleIn 0.4s 0.4s forwards; }}
    .plot-box {{ background: {c['bg_card']}; border-radius: 22px; padding: 22px;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 8px 28px rgba(0,0,0,0.06);
                 opacity: 0; animation: fadeIn 0.5s 0.4s forwards; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 16px 28px; justify-content: center; margin-top: 28px; }}
    .legend-item {{ display: flex; align-items: center; gap: 10px; font-size: 28px;
                    color: {c['text_body']}; font-weight: 600; }}
    .ldot {{ width: 18px; height: 18px; border-radius: 50%; }}
    .axis-label {{ font-size: 22px; fill: {c['text_muted']}; font-weight: 600; }}
    .callout-box {{ position: absolute; bottom: 80px; left: 50px; right: 50px;
                    background: {_hex_to_rgba(c['blue'], 0.08)};
                    border: 1.5px solid {_hex_to_rgba(c['blue'], 0.25)};
                    border-radius: 18px; padding: 26px 30px; text-align: center;
                    box-shadow: 0 4px 20px {_hex_to_rgba(c['blue'], 0.08)}; }}
    .callout-text {{ font-size: 28px; color: {c['text_dark']}; font-weight: 600; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
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

def equation_scene(data: dict, theme: dict, timing: SceneTiming | None = None) -> str:
    c = _tc(theme)
    header = _esc(data["header"])
    latex = data["latex"]
    explanation = data.get("explanation", "")
    callout = data.get("callout", "")

    css = f"""
    .scene {{ background: linear-gradient(160deg, {c['bg']} 0%, #e9eff6 50%, #f2f5f8 100%);
              padding: 100px 60px; justify-content: center; align-items: center; }}
    .eq-container {{ position: relative; z-index: 2; text-align: center; width: 100%; }}
    .header {{ font-size: 50px; font-weight: 900; color: {c['text_dark']};
               letter-spacing: -1px;
               margin-bottom: 50px; opacity: 0; animation: fadeInUp 0.65s 0.2s forwards; }}
    .eq-box {{ background: {c['bg_card']}; border-radius: 26px; padding: 54px 40px;
               box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 12px 40px rgba(0,0,0,0.08);
               border: 1px solid {c['border']};
               opacity: 0; animation: popIn 0.7s 0.6s forwards; }}
    .eq-text {{ font-size: 40px; color: {c['text_dark']};
                font-family: 'JetBrains Mono', monospace; line-height: 1.6;
                word-break: break-all; }}
    .explanation {{ font-size: 32px; color: {c['text_body']}; line-height: 1.55;
                    margin-top: 46px; opacity: 0; animation: fadeIn 0.7s 1.2s forwards; }}
    .callout-box {{ position: absolute; bottom: 100px; left: 60px; right: 60px;
                    background: {_hex_to_rgba(c['blue'], 0.08)};
                    border: 1.5px solid {_hex_to_rgba(c['blue'], 0.25)};
                    border-radius: 18px; padding: 30px 34px; text-align: center;
                    box-shadow: 0 4px 20px {_hex_to_rgba(c['blue'], 0.08)};
                    opacity: 0; animation: fadeInUp 0.5s 1.6s forwards; }}
    .callout-text {{ font-size: 30px; color: {c['text_dark']}; font-weight: 600; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
        <div class="gradient-orb orb1" style="width:500px;height:500px;top:150px;right:-100px;
             background:radial-gradient(circle, {_hex_to_rgba(c['blue'], 0.08)}, transparent 70%)"></div>
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

def pipeline_diagram_scene(data: dict, theme: dict, timing: SceneTiming | None = None) -> str:
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
    .scene {{ background: linear-gradient(160deg, {c['bg']} 0%, #e9eff6 50%, #f2f5f8 100%);
              padding: 80px 50px; }}
    .header {{ font-size: 50px; font-weight: 900; color: {c['text_dark']};
               text-align: center; letter-spacing: -1px;
               opacity: 0; animation: fadeInUp 0.65s 0.15s forwards; }}
    .header-line {{ width: 70px; height: 5px; margin: 18px auto 36px;
        background: {c['blue']}; border-radius: 3px;
        opacity: 0; animation: scaleIn 0.4s 0.4s forwards; }}
    .pipe {{ display: flex; flex-direction: column; align-items: center; gap: 16px; }}
    .side {{ width: 90%; border-radius: 22px; padding: 30px 34px; text-align: center;
             background: {c['bg_card']};
             box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.06); }}
    .side-title {{ font-size: 34px; font-weight: 700; }}
    .side-sub {{ font-size: 24px; color: {c['text_muted']}; margin-top: 6px; }}
    .arrow {{ font-size: 32px; color: {c['text_muted']}; }}
    .center {{ width: 90%; border-radius: 22px; padding: 34px;
               background: {c['bg_card']}; border: 2.5px solid {c['orange']};
               box-shadow: 0 4px 12px rgba(0,0,0,0.04), 0 12px 36px {_hex_to_rgba(c['orange'], 0.12)}; }}
    .center-title {{ font-size: 36px; font-weight: 900; color: {c['orange']};
                     text-align: center; margin-bottom: 20px; }}
    .ci {{ font-size: 27px; color: {c['text_body']}; padding: 12px 0;
           border-bottom: 1px solid {c['border']}; display: flex; gap: 12px; align-items: center; }}
    .ci:last-child {{ border-bottom: none; }}
    .ci-num {{ width: 30px; height: 30px; border-radius: 50%; background: {_hex_to_rgba(c['orange'], 0.15)};
               color: {c['orange']}; font-size: 16px; font-weight: 800; flex-shrink: 0;
               display: flex; align-items: center; justify-content: center; }}
    .callout-box {{ position: absolute; bottom: 80px; left: 50px; right: 50px;
                    background: {_hex_to_rgba(c['green'], 0.08)};
                    border: 1.5px solid {_hex_to_rgba(c['green'], 0.25)};
                    border-radius: 18px; padding: 26px 30px; text-align: center;
                    box-shadow: 0 4px 20px {_hex_to_rgba(c['green'], 0.08)}; }}
    .callout-text {{ font-size: 28px; color: {c['text_dark']}; font-weight: 600; }}
    """

    body = f"""<div class="scene">
        <div class="bg-dots"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
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

def closing_scene(data: dict, theme: dict, timing: SceneTiming | None = None,
                  branding: dict | None = None) -> str:
    c = _tc(theme)
    title = _esc(data.get("title", "Key References"))
    refs = data.get("references", [])
    branding = branding or {}
    # CTA priority: scene-level > branding-level > default
    cta_text = (data.get("cta_text") or branding.get("cta_text")
                or "Follow for more science!")
    channel_name = branding.get("channel_name", "")
    social_handles = branding.get("social_handles", [])

    refs_html = ""
    for i, ref in enumerate(refs):
        delay = 0.9 + i * 0.2
        refs_html += f"""
        <div class="ref anim-item" style="animation-name: fadeIn; animation-delay: {delay:.2f}s">
            <span class="ref-num">{i+1}</span> {_esc(ref)}
        </div>"""

    cta_delay = 0.9 + len(refs) * 0.2 + 0.5

    socials_delay = cta_delay + 0.5
    channel_delay = socials_delay + 0.3

    # Social handles HTML
    socials_html = ""
    if social_handles:
        handles = " &nbsp;&middot;&nbsp; ".join(_esc(h) for h in social_handles)
        socials_html = (f'<div class="socials anim-item" '
                        f'style="animation-name: fadeInUp; animation-delay: {socials_delay:.2f}s">'
                        f'{handles}</div>')

    # Channel name HTML
    channel_html = ""
    if channel_name:
        channel_html = (f'<div class="channel-name anim-item" '
                        f'style="animation-name: fadeInUp; animation-delay: {channel_delay:.2f}s">'
                        f'{_esc(channel_name)}</div>')

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
            background: linear-gradient(90deg, {c['blue']}, {c['cyan']}, {c['blue']});
            background-size: 200% 100%;
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text;
            opacity: 0; animation: fadeInUp 0.6s {cta_delay:.2f}s forwards, gradientShift 3s {cta_delay+0.6:.2f}s ease-in-out infinite; }}
    .socials {{ font-size: 24px; color: rgba(255,255,255,0.45); margin-top: 24px;
                letter-spacing: 0.5px; }}
    .channel-name {{ font-size: 30px; font-weight: 700; color: rgba(255,255,255,0.7);
                     margin-top: 18px; letter-spacing: 1px; }}
    .bottom-bar {{ position: absolute; bottom: 0; left: 0; right: 0; height: 6px;
        background: linear-gradient(90deg, {c['blue']}, {c['green']}, {c['orange']});
        opacity: 0; animation: fadeIn 0.8s {cta_delay + 0.3:.2f}s forwards; }}
    """

    body = f"""<div class="scene">
        <div class="bg-grid"></div>
        <div class="bg-noise"></div>
        <div class="vignette"></div>
        <div class="gradient-orb orb1" style="width:600px;height:600px;top:-80px;right:-120px;
             background:radial-gradient(circle, {_hex_to_rgba(c['blue'], 0.14)}, transparent 70%)"></div>
        <div class="gradient-orb orb2" style="width:400px;height:400px;bottom:100px;left:-100px;
             background:radial-gradient(circle, {_hex_to_rgba(c['green'], 0.1)}, transparent 70%);animation-delay:0.5s"></div>
        <div class="close-container">
            <div class="title">{title}</div>
            <div class="divider"></div>
            <div class="refs">{refs_html}</div>
            <div class="cta">{_esc(cta_text)}</div>
            {socials_html}
            {channel_html}
        </div>
        <div class="bottom-bar"></div>
    </div>"""

    return _wrap_page(body, css, c["bg_dark"], branding=branding)


# ── Dispatcher ────────────────────────────────────────────────────────────────

# Scenes that accept branding kwarg
_BRANDING_SCENES = {"hook", "closing"}

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


def render_scene_html(scene_data: dict, theme: dict,
                      timing: SceneTiming | None = None,
                      branding: dict | None = None) -> str:
    """Render a scene to a production-quality HTML string.

    When *timing* is provided, element animation delays are driven by
    narration chunk durations instead of hardcoded CSS values.
    When *branding* is provided, watermark/CTA/channel info is injected.
    """
    scene_type = scene_data.get("type", "")
    renderer = SCENE_RENDERERS.get(scene_type)
    if renderer is None:
        return ""
    if scene_type in _BRANDING_SCENES:
        return renderer(scene_data, theme, timing=timing, branding=branding)
    return renderer(scene_data, theme, timing=timing)
