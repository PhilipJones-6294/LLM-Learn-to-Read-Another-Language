#!/usr/bin/env python3
"""
Cognitive Gradient Engine — Tailscale web reader.

Serves the gradient novel output as a clean, chapter-navigable web page
accessible from any device on your Tailscale network.

Run from the project root:
    python reader.py
    python reader.py --port 8080
    python reader.py --file data/output/hp1_gradient.txt

Then on any Tailscale device open:
    http://<your-tailscale-ip>:8080

Find your Tailscale IP:
    tailscale ip -4
"""

import argparse
import os
import re
import sys
from typing import List, Dict

# ── Allow running as python reader.py from project root ───────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cognitive_gradient.config as config

from flask import Flask, abort, redirect, render_template_string, url_for

app = Flask(__name__)

# ── Chapter detection (mirrors segmenter.py) ──────────────────────────────────
CHAPTER_PATTERN = re.compile(
    r"^(chapter\s+\w+|chapter\s+\d+|\d+\.\s+\w+|[IVXLCDM]+\.\s+\w+)",
    re.IGNORECASE,
)

# French-only function words (absent from English) used for language-mix estimate
FRENCH_MARKERS = frozenset({
    "le", "la", "les", "du", "des", "une", "et", "il", "elle", "ils",
    "elles", "je", "nous", "vous", "qui", "que", "dans", "avec", "pour",
    "par", "au", "aux", "dit", "avait", "lui", "mais", "aussi", "donc",
    "très", "même", "était", "être", "avoir", "comme", "sur", "pas",
    "plus", "bien", "tout", "quand", "alors", "encore",
})

# ── Novel loading ──────────────────────────────────────────────────────────────

def load_chapters(path: str) -> List[Dict]:
    """
    Parse the gradient novel output file into chapter dicts.

    Returns:
        [{"index": 1, "heading": "Chapter One", "paragraphs": [...], "french_pct": 0.42}, ...]
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()

    blocks = [b.strip() for b in re.split(r"\n\n+", text) if b.strip()]

    chapters: List[Dict] = []
    current_heading = ""
    current_paragraphs: List[str] = []

    def flush():
        if current_paragraphs:
            chapter_text = " ".join(current_paragraphs)
            chapters.append({
                "index": len(chapters) + 1,
                "heading": current_heading or f"Chapter {len(chapters) + 1}",
                "paragraphs": list(current_paragraphs),
                "french_pct": _french_pct(chapter_text),
            })

    for block in blocks:
        if CHAPTER_PATTERN.match(block):
            flush()
            current_heading = block
            current_paragraphs = []
        else:
            current_paragraphs.append(block)

    flush()

    if not chapters:
        chapters.append({
            "index": 1,
            "heading": "Novel",
            "paragraphs": blocks,
            "french_pct": _french_pct(text),
        })

    return chapters


def _french_pct(text: str) -> float:
    """
    Estimate the proportion of the text that is French.

    Counts French-only function words as a fraction of total words, then
    scales to a 0–100 percentage. Fully French text sits around 25–30%
    French markers; fully English sits near 0%.
    """
    words = re.findall(r"[a-zA-ZÀ-ÿ]+", text.lower())
    if not words:
        return 0.0
    french_count = sum(1 for w in words if w in FRENCH_MARKERS)
    raw = french_count / len(words)
    # Scale: 0.28 French markers ≈ fully French → map to 100%
    return round(min(raw / 0.28, 1.0) * 100, 1)


# ── HTML template ──────────────────────────────────────────────────────────────

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ chapter.heading }} — {{ novel_title }}</title>
  <style>
    :root {
      --bg: #f5f0e8;
      --text: #2c2416;
      --muted: #8a7a62;
      --accent: #4a7c59;
      --border: #d8cfc0;
      --bar-en: #b8995a;
      --bar-fr: #4a7c59;
      --max-w: 680px;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #1a1612;
        --text: #e8dfc8;
        --muted: #8a7a62;
        --accent: #6aac82;
        --border: #3a3228;
        --bar-en: #b8995a;
        --bar-fr: #6aac82;
      }
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: Georgia, 'Palatino Linotype', serif;
      font-size: 1.1rem;
      line-height: 1.8;
      padding: 0 1rem 4rem;
    }
    /* ── Top bar ── */
    .topbar {
      position: sticky; top: 0; z-index: 10;
      background: var(--bg);
      border-bottom: 1px solid var(--border);
      padding: .5rem 0;
      display: flex; align-items: center; gap: 1rem;
      max-width: var(--max-w); margin: 0 auto;
    }
    .topbar a { color: var(--accent); text-decoration: none; font-size: .9rem; }
    .topbar a:hover { text-decoration: underline; }
    .chapter-select {
      font-family: inherit; font-size: .9rem;
      background: transparent; border: 1px solid var(--border);
      color: var(--text); padding: .25rem .5rem; border-radius: 4px;
      cursor: pointer; flex: 1;
    }
    /* ── Novel progress bar ── */
    .progress-wrap {
      max-width: var(--max-w); margin: .75rem auto .25rem;
    }
    .progress-label {
      font-size: .75rem; color: var(--muted);
      display: flex; justify-content: space-between; margin-bottom: .25rem;
    }
    .progress-track {
      height: 6px; border-radius: 3px;
      background: var(--bar-en);
      overflow: hidden;
    }
    .progress-fill {
      height: 100%; border-radius: 3px;
      background: var(--bar-fr);
      transition: width .3s ease;
    }
    /* ── Chapter header ── */
    .chapter-header {
      max-width: var(--max-w); margin: 2rem auto 1.5rem;
    }
    h1 { font-size: 1.4rem; font-weight: normal; letter-spacing: .04em; }
    .lang-badge {
      display: inline-block; margin-top: .4rem;
      font-size: .75rem; font-family: system-ui, sans-serif;
      color: var(--muted); letter-spacing: .06em;
    }
    /* ── Body text ── */
    .chapter-body { max-width: var(--max-w); margin: 0 auto; }
    .chapter-body p { margin-bottom: 1.2em; text-align: justify; }
    /* ── Navigation ── */
    .nav {
      max-width: var(--max-w); margin: 3rem auto 0;
      display: flex; justify-content: space-between; align-items: center;
      border-top: 1px solid var(--border); padding-top: 1.5rem;
    }
    .nav a {
      color: var(--accent); text-decoration: none; font-size: .95rem;
    }
    .nav a:hover { text-decoration: underline; }
    .nav span { color: var(--muted); font-size: .85rem; }
  </style>
</head>
<body>

<div class="topbar">
  <a href="{{ url_for('index') }}">{{ novel_title }}</a>
  <select class="chapter-select" onchange="location.href=this.value">
    {% for ch in all_chapters %}
    <option value="{{ url_for('chapter', n=ch.index) }}"
            {{ 'selected' if ch.index == chapter.index else '' }}>
      {{ ch.heading }}
    </option>
    {% endfor %}
  </select>
</div>

<div class="progress-wrap">
  <div class="progress-label">
    <span>English</span>
    <span>Novel position: chapter {{ chapter.index }} of {{ total_chapters }}</span>
    <span>French</span>
  </div>
  <div class="progress-track">
    <div class="progress-fill" style="width: {{ novel_pct }}%"></div>
  </div>
</div>

<div class="chapter-header">
  <h1>{{ chapter.heading }}</h1>
  <span class="lang-badge">
    {{ chapter.french_pct }}% French content
    &nbsp;·&nbsp;
    {{ chapter.paragraphs | length }} paragraph{{ 's' if chapter.paragraphs | length != 1 else '' }}
  </span>
</div>

<div class="chapter-body">
  {% for para in chapter.paragraphs %}
  <p>{{ para }}</p>
  {% endfor %}
</div>

<div class="nav">
  {% if chapter.index > 1 %}
  <a href="{{ url_for('chapter', n=chapter.index - 1) }}">← Previous</a>
  {% else %}
  <span></span>
  {% endif %}

  <span>{{ chapter.index }} / {{ total_chapters }}</span>

  {% if chapter.index < total_chapters %}
  <a href="{{ url_for('chapter', n=chapter.index + 1) }}">Next →</a>
  {% else %}
  <span></span>
  {% endif %}
</div>

</body>
</html>"""


# ── State (loaded once on startup) ────────────────────────────────────────────

_chapters: List[Dict] = []
_novel_title: str = ""
_output_path: str = ""


def _load(path: str) -> None:
    global _chapters, _novel_title, _output_path
    _output_path = path
    _novel_title = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
    _chapters = load_chapters(path)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("chapter", n=1))


@app.route("/chapter/<int:n>")
def chapter(n: int):
    if not _chapters:
        abort(503, "No novel loaded — run the gradient pipeline first.")
    if n < 1 or n > len(_chapters):
        abort(404)

    ch = _chapters[n - 1]
    total = len(_chapters)
    # Novel position as fraction (used to fill the progress bar)
    novel_pct = round((n - 1) / max(total - 1, 1) * 100, 1)

    return render_template_string(
        _TEMPLATE,
        chapter=ch,
        all_chapters=_chapters,
        total_chapters=total,
        novel_pct=novel_pct,
        novel_title=_novel_title,
    )


@app.route("/api/chapters")
def api_chapters():
    from flask import jsonify
    return jsonify([
        {"index": c["index"], "heading": c["heading"], "french_pct": c["french_pct"]}
        for c in _chapters
    ])


# ── Entry point ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cognitive Gradient — web reader")
    parser.add_argument(
        "--file", default=config.OUTPUT_PATH,
        metavar="PATH",
        help=f"Gradient novel to serve (default: {config.OUTPUT_PATH})",
    )
    parser.add_argument(
        "--port", type=int, default=8080,
        help="Port to listen on (default: 8080)",
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0 — accessible via Tailscale)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if not os.path.exists(args.file):
        print(f"Error: output file not found: {args.file}")
        print("Run the gradient pipeline first:  python run.py")
        sys.exit(1)

    _load(args.file)

    print(f"Loaded {len(_chapters)} chapters from {args.file}")
    print()
    print(f"  Reader running at  http://localhost:{args.port}")
    print(f"  Tailscale access   http://$(tailscale ip -4):{args.port}")
    print()
    print("  Press Ctrl+C to stop.")
    print()

    app.run(host=args.host, port=args.port, debug=False)
