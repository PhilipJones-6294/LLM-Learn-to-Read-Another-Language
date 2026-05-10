#!/usr/bin/env python3
"""
reader.py — Gradient Reader

Standalone Flask app. Serves the audio-synced gradient reader interface.
No cognitive_gradient imports — reads library files only.

Library structure expected at data/output/<book_name>/:
    meta.json
    ch01/
        text.txt
        audio.mp3
        sync.json
    ch02/ ...

Usage:
    python reader.py
    python reader.py --port 5001 --host 0.0.0.0
    python reader.py --library /path/to/data/output
"""

import argparse
import json
import os
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

LIBRARY_ROOT = Path(__file__).resolve().parent / "data" / "output"

# ─────────────────────────────────────────────
# FLASK APP
# ─────────────────────────────────────────────

app = Flask(__name__)


# ─────────────────────────────────────────────
# LIBRARY API
# ─────────────────────────────────────────────

def _get_library_root() -> Path:
    return LIBRARY_ROOT


def _list_books():
    root = _get_library_root()
    books = []
    if not root.exists():
        return books
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            books.append({
                "name":    meta.get("name", d.name),
                "title":   meta.get("title", d.name),
                "author":  meta.get("author", ""),
                "voice":   meta.get("voice", ""),
                "chapters": meta.get("total_chapters", len(meta.get("chapters", []))),
                "generated": meta.get("generated", ""),
            })
        except Exception:
            pass
    return books


@app.route("/api/books")
def api_books():
    return jsonify(_list_books())


@app.route("/api/books/<book_name>/meta")
def api_book_meta(book_name):
    meta_path = _get_library_root() / book_name / "meta.json"
    if not meta_path.exists():
        return jsonify({"error": "not found"}), 404
    return jsonify(json.loads(meta_path.read_text(encoding="utf-8")))


@app.route("/api/books/<book_name>/chapters/<int:ch_num>/text")
def api_chapter_text(book_name, ch_num):
    ch_dir = _get_library_root() / book_name / f"ch{ch_num:02d}"
    text_path = ch_dir / "text.txt"
    if not text_path.exists():
        return jsonify({"error": "not found"}), 404
    return jsonify({"text": text_path.read_text(encoding="utf-8", errors="replace")})


@app.route("/api/books/<book_name>/chapters/<int:ch_num>/sync")
def api_chapter_sync(book_name, ch_num):
    ch_dir = _get_library_root() / book_name / f"ch{ch_num:02d}"
    sync_path = ch_dir / "sync.json"
    if not sync_path.exists():
        return jsonify({"error": "not found"}), 404
    return jsonify(json.loads(sync_path.read_text(encoding="utf-8")))


@app.route("/api/books/<book_name>/chapters/<int:ch_num>/audio")
def api_chapter_audio(book_name, ch_num):
    """Serve audio with range request support for seeking."""
    ch_dir = _get_library_root() / book_name / f"ch{ch_num:02d}"
    audio_path = ch_dir / "audio.mp3"
    if not audio_path.exists():
        return jsonify({"error": "not found"}), 404

    file_size = audio_path.stat().st_size
    range_header = request.headers.get("Range", None)

    if range_header is None:
        # Full file
        return send_file(audio_path, mimetype="audio/mpeg")

    # Parse range header: bytes=start-end
    byte_range = range_header.replace("bytes=", "").strip()
    parts = byte_range.split("-")
    range_start = int(parts[0]) if parts[0] else 0
    range_end   = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
    range_end   = min(range_end, file_size - 1)
    length      = range_end - range_start + 1

    def generate_chunk():
        with open(audio_path, "rb") as f:
            f.seek(range_start)
            remaining = length
            chunk_size = 64 * 1024  # 64 KB
            while remaining > 0:
                data = f.read(min(chunk_size, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range":  f"bytes {range_start}-{range_end}/{file_size}",
        "Accept-Ranges":  "bytes",
        "Content-Length": str(length),
        "Content-Type":   "audio/mpeg",
    }
    return Response(generate_chunk(), status=206, headers=headers)


# ─────────────────────────────────────────────
# HTML APP
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return HTML_APP


HTML_APP = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gradient Reader</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=Inter:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:         #f5f0e8;
    --bg2:        #ede7d9;
    --bg3:        #e4ddd0;
    --surface:    #faf7f2;
    --border:     #d6cfc4;
    --border2:    #c8bfb2;
    --text:       #3d3530;
    --text2:      #6b6057;
    --text3:      #9c9189;
    --accent:     #8b7355;
    --highlight:  #f0c060;
    --highlight2: rgba(240, 192, 96, 0.25);
    --shadow:     0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04);
    --radius:     10px;
    --font-size:  18px;
    --line-height: 1.85;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Lora', serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── HEADER ─────────────────────────────── */
  header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0 24px;
    display: flex;
    align-items: center;
    gap: 16px;
    height: 56px;
    flex-shrink: 0;
  }
  .wordmark {
    font-family: 'Lora', serif;
    font-size: 16px;
    font-weight: 500;
    color: var(--text);
    white-space: nowrap;
  }
  .wordmark span { color: var(--text3); font-style: italic; font-weight: 400; }
  .book-title {
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    color: var(--text2);
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .header-actions { display: flex; gap: 8px; align-items: center; }
  .icon-btn {
    background: none;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-family: 'Inter', sans-serif;
    color: var(--text2);
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .icon-btn:hover { background: var(--bg2); border-color: var(--border2); color: var(--text); }

  /* ── CONTROLS BAR ───────────────────────── */
  .controls {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 10px 24px;
    display: flex;
    align-items: center;
    gap: 14px;
    flex-shrink: 0;
  }
  .controls.hidden { display: none; }

  /* Play/Pause */
  #play-btn {
    width: 40px; height: 40px;
    border-radius: 50%;
    background: var(--accent);
    border: none;
    color: var(--surface);
    font-size: 16px;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    transition: all 0.15s;
  }
  #play-btn:hover { background: #7a6448; }
  #play-btn:disabled { opacity: 0.4; cursor: default; }

  /* Skip buttons */
  .skip-btn {
    background: none;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    font-family: 'Inter', sans-serif;
    color: var(--text2);
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .skip-btn:hover { background: var(--bg2); color: var(--text); }

  /* Progress */
  .progress-wrap {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }
  #progress-bar {
    width: 100%;
    height: 4px;
    border-radius: 2px;
    background: var(--bg3);
    appearance: none;
    cursor: pointer;
    accent-color: var(--accent);
  }
  #progress-bar::-webkit-slider-thumb { cursor: pointer; }
  .time-row {
    display: flex;
    justify-content: space-between;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px;
    color: var(--text3);
  }

  /* Speed */
  .speed-wrap { display: flex; gap: 4px; align-items: center; flex-shrink: 0; }
  .speed-label {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    color: var(--text3);
  }
  .speed-btn {
    padding: 4px 8px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text2);
    font-size: 11.5px;
    font-family: 'Inter', sans-serif;
    cursor: pointer;
    transition: all 0.15s;
  }
  .speed-btn.active {
    background: var(--bg2);
    border-color: var(--accent);
    color: var(--accent);
    font-weight: 500;
  }
  .speed-btn:hover:not(.active) { background: var(--bg2); }

  /* Chapter nav */
  .ch-nav { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
  .ch-nav-btn {
    background: none;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    font-family: 'Inter', sans-serif;
    color: var(--text2);
    cursor: pointer;
    transition: all 0.15s;
  }
  .ch-nav-btn:hover:not(:disabled) { background: var(--bg2); color: var(--text); }
  .ch-nav-btn:disabled { opacity: 0.35; cursor: default; }
  .ch-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text3);
    white-space: nowrap;
    min-width: 60px;
    text-align: center;
  }

  /* Font size */
  .font-wrap { display: flex; gap: 4px; align-items: center; flex-shrink: 0; }
  .font-btn {
    padding: 4px 8px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text2);
    font-size: 12px;
    font-family: 'Inter', sans-serif;
    cursor: pointer;
    transition: all 0.15s;
  }
  .font-btn:hover { background: var(--bg2); }

  /* ── READER AREA ─────────────────────────── */
  .reader-wrap {
    flex: 1;
    overflow-y: auto;
    padding: 48px 0 80px;
    scroll-behavior: smooth;
  }
  .reader-wrap::-webkit-scrollbar { width: 6px; }
  .reader-wrap::-webkit-scrollbar-track { background: transparent; }
  .reader-wrap::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }

  #reader-content {
    max-width: 680px;
    margin: 0 auto;
    padding: 0 32px;
  }

  .chapter-heading {
    font-family: 'Lora', serif;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text3);
    text-align: center;
    margin-bottom: 40px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }

  /* Sentences */
  .sentence {
    font-size: var(--font-size);
    line-height: var(--line-height);
    color: var(--text);
    cursor: pointer;
    border-radius: 4px;
    padding: 1px 4px;
    margin: 0 -4px;
    transition: background 0.15s;
    display: inline;
  }
  .sentence:hover { background: var(--bg3); }
  .sentence.active {
    background: var(--highlight2);
    border-bottom: 2px solid var(--highlight);
  }

  /* Paragraph spacing between sentence groups */
  .para-break {
    display: block;
    height: 1em;
  }

  /* ── LIBRARY PANEL ──────────────────────── */
  #library-panel {
    position: fixed;
    top: 56px; right: 0; bottom: 0;
    width: 320px;
    background: var(--surface);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    transform: translateX(320px);
    transition: transform 0.2s ease;
    z-index: 20;
    box-shadow: -4px 0 16px rgba(0,0,0,0.06);
  }
  #library-panel.open { transform: translateX(0); }
  .panel-header {
    padding: 14px 16px 10px;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text3);
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .panel-close {
    background: none; border: none; color: var(--text3);
    cursor: pointer; font-size: 16px; padding: 0 2px;
  }
  .book-list { flex: 1; overflow-y: auto; padding: 8px 0; }
  .book-item {
    padding: 12px 16px;
    cursor: pointer;
    border-left: 3px solid transparent;
    transition: all 0.12s;
  }
  .book-item:hover { background: var(--bg2); }
  .book-item.active { border-left-color: var(--accent); background: var(--bg2); }
  .book-item-title {
    font-family: 'Lora', serif;
    font-size: 14px;
    color: var(--text);
    font-weight: 500;
  }
  .book-item-meta {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    color: var(--text3);
    margin-top: 2px;
  }

  /* Chapter list inside panel */
  .ch-list { padding: 8px 0; border-top: 1px solid var(--border); }
  .ch-item {
    padding: 8px 16px 8px 28px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    font-size: 12.5px;
    color: var(--text2);
    transition: all 0.12s;
    border-left: 3px solid transparent;
  }
  .ch-item:hover { background: var(--bg2); color: var(--text); }
  .ch-item.active { border-left-color: var(--accent); color: var(--accent); font-weight: 500; }

  /* ── LOADING / EMPTY STATES ─────────────── */
  .empty-state {
    max-width: 400px;
    margin: 80px auto;
    text-align: center;
    padding: 0 32px;
  }
  .empty-title {
    font-family: 'Lora', serif;
    font-size: 22px;
    color: var(--text);
    margin-bottom: 12px;
  }
  .empty-sub {
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    color: var(--text3);
    line-height: 1.6;
  }
  .loading-msg {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--text3);
    text-align: center;
    padding: 40px 0;
  }

  /* ── TOAST ──────────────────────────────── */
  #toast {
    position: fixed;
    bottom: 24px; left: 50%;
    transform: translateX(-50%) translateY(20px);
    background: var(--text);
    color: var(--surface);
    padding: 8px 18px;
    border-radius: 20px;
    font-size: 13px;
    font-family: 'Inter', sans-serif;
    opacity: 0;
    transition: all 0.25s;
    pointer-events: none;
    z-index: 100;
  }
  #toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

  /* ── MOBILE ─────────────────────────────── */
  @media (max-width: 640px) {
    header { padding: 0 14px; gap: 10px; }
    .controls { padding: 8px 14px; gap: 8px; flex-wrap: wrap; }
    .speed-wrap, .font-wrap { display: none; }
    .progress-wrap { order: 10; width: 100%; flex: none; }
    #reader-content { padding: 0 18px; }
    .sentence { font-size: 17px; }
    #library-panel { width: 100%; }
  }
</style>
</head>
<body>

<header>
  <div class="wordmark">Gradient <span>Reader</span></div>
  <div class="book-title" id="header-title">No book loaded</div>
  <div class="header-actions">
    <button class="icon-btn" id="library-btn">Library</button>
  </div>
</header>

<div class="controls hidden" id="controls">
  <!-- Chapter nav -->
  <div class="ch-nav">
    <button class="ch-nav-btn" id="prev-ch-btn">‹</button>
    <span class="ch-label" id="ch-label">Ch 1</span>
    <button class="ch-nav-btn" id="next-ch-btn">›</button>
  </div>

  <!-- Play/Pause -->
  <button id="play-btn" disabled>▶</button>

  <!-- Skip -->
  <button class="skip-btn" id="rw-btn">« 15s</button>
  <button class="skip-btn" id="ff-btn">15s »</button>

  <!-- Progress -->
  <div class="progress-wrap">
    <input type="range" id="progress-bar" min="0" max="1000" value="0">
    <div class="time-row">
      <span id="time-current">0:00</span>
      <span id="time-total">0:00</span>
    </div>
  </div>

  <!-- Speed -->
  <div class="speed-wrap">
    <span class="speed-label">Speed</span>
    <button class="speed-btn" data-speed="0.75">0.75×</button>
    <button class="speed-btn active" data-speed="1">1×</button>
    <button class="speed-btn" data-speed="1.25">1.25×</button>
    <button class="speed-btn" data-speed="1.5">1.5×</button>
    <button class="speed-btn" data-speed="2">2×</button>
  </div>

  <!-- Font size -->
  <div class="font-wrap">
    <button class="font-btn" id="font-down">A−</button>
    <button class="font-btn" id="font-up">A+</button>
  </div>
</div>

<!-- Reader -->
<div class="reader-wrap" id="reader-wrap">
  <div id="reader-content">
    <div class="empty-state">
      <div class="empty-title">Gradient Reader</div>
      <div class="empty-sub">Open the Library to choose a book.</div>
    </div>
  </div>
</div>

<!-- Library panel -->
<div id="library-panel">
  <div class="panel-header">
    Library
    <button class="panel-close" id="panel-close">✕</button>
  </div>
  <div class="book-list" id="book-list"></div>
</div>

<div id="toast"></div>

<!-- Hidden audio element -->
<audio id="audio" preload="none"></audio>

<script>
// ── STATE ──────────────────────────────────────────────────────
const state = {
  books:        [],
  currentBook:  null,
  currentCh:    1,
  totalChs:     0,
  sync:         [],   // [{index, text, start, end}]
  activeSentIdx: -1,
  fontSize:     18,
  rafId:        null,
};

const audio = document.getElementById('audio');

// ── LIBRARY ────────────────────────────────────────────────────
async function loadLibrary() {
  try {
    const res = await fetch('/api/books');
    state.books = await res.json();
    renderBookList();
  } catch(e) {
    showToast('Could not load library');
  }
}

function renderBookList() {
  const list = document.getElementById('book-list');
  list.innerHTML = '';
  if (state.books.length === 0) {
    list.innerHTML = '<div class="loading-msg">No books found.<br>Run generate_sync.py first.</div>';
    return;
  }
  state.books.forEach(book => {
    const item = document.createElement('div');
    item.className = 'book-item' + (state.currentBook?.name === book.name ? ' active' : '');
    item.innerHTML =
      `<div class="book-item-title">${book.title}</div>` +
      `<div class="book-item-meta">${book.author} · ${book.chapters} chapters · ${book.voice}</div>`;
    item.addEventListener('click', () => openBook(book));
    list.appendChild(item);
  });
}

async function openBook(book) {
  state.currentBook = book;
  state.totalChs    = book.chapters;
  state.currentCh   = 1;
  document.getElementById('header-title').textContent = book.title;
  renderBookList();
  await loadChapter(1);
  document.getElementById('library-panel').classList.remove('open');
}

// ── CHAPTER LOADING ────────────────────────────────────────────
async function loadChapter(chNum) {
  if (!state.currentBook) return;
  const name = state.currentBook.name;

  // Stop current audio
  audio.pause();
  audio.src = '';
  cancelAnimationFrame(state.rafId);
  state.activeSentIdx = -1;

  // Update controls
  state.currentCh = chNum;
  document.getElementById('ch-label').textContent = `Ch ${chNum}`;
  document.getElementById('prev-ch-btn').disabled = chNum <= 1;
  document.getElementById('next-ch-btn').disabled = chNum >= state.totalChs;
  document.getElementById('play-btn').disabled = true;
  document.getElementById('play-btn').textContent = '▶';

  // Show loading
  const content = document.getElementById('reader-content');
  content.innerHTML = '<div class="loading-msg">Loading chapter…</div>';

  try {
    // Fetch text + sync in parallel
    const [textRes, syncRes, metaRes] = await Promise.all([
      fetch(`/api/books/${name}/chapters/${chNum}/text`),
      fetch(`/api/books/${name}/chapters/${chNum}/sync`),
      fetch(`/api/books/${name}/meta`),
    ]);

    const textData = await textRes.json();
    const syncData = await syncRes.json();
    const metaData = await metaRes.json();

    state.sync = syncData;

    // Find chapter heading from meta
    const chMeta = metaData.chapters?.find(c => c.index === chNum) || {};
    const heading = chMeta.heading || `Chapter ${chNum}`;

    renderChapter(heading, syncData);

    // Set up audio
    audio.src = `/api/books/${name}/chapters/${chNum}/audio`;
    audio.load();
    audio.playbackRate = parseFloat(
      document.querySelector('.speed-btn.active')?.dataset.speed || '1'
    );

    audio.addEventListener('loadedmetadata', onAudioMeta, { once: true });
    audio.addEventListener('error', () => showToast('Audio error'), { once: true });

    document.getElementById('controls').classList.remove('hidden');
    document.getElementById('play-btn').disabled = false;

  } catch(e) {
    content.innerHTML = '<div class="loading-msg">Error loading chapter.</div>';
    showToast('Error: ' + e.message);
  }
}

function onAudioMeta() {
  document.getElementById('time-total').textContent = fmtTime(audio.duration);
  document.getElementById('progress-bar').max = Math.floor(audio.duration);
}

// ── RENDER CHAPTER ─────────────────────────────────────────────
function renderChapter(heading, sync) {
  const content = document.getElementById('reader-content');
  content.innerHTML = '';

  // Heading
  const h = document.createElement('div');
  h.className = 'chapter-heading';
  h.textContent = heading;
  content.appendChild(h);

  // Sentences — rendered inline with paragraph breaks
  const para = document.createElement('p');
  para.style.cssText = 'font-size:var(--font-size);line-height:var(--line-height);';

  sync.forEach((item, i) => {
    // Paragraph break heuristic: if previous sentence ended with paragraph-
    // ending punctuation and this one starts fresh, insert a break.
    if (i > 0) {
      const prev = sync[i - 1].text;
      const startsNew = /^["'—\u201C]/.test(item.text) ||
                        (prev.endsWith('"') && /^[A-Z]/.test(item.text));
      if (startsNew) {
        content.appendChild(para.cloneNode(true));
        para.innerHTML = '';
      }
    }

    const span = document.createElement('span');
    span.className = 'sentence';
    span.dataset.idx = i;
    span.textContent = item.text + ' ';
    span.addEventListener('click', () => seekToSentence(i));
    para.appendChild(span);
  });

  content.appendChild(para);
}

// ── SYNC LOOP ──────────────────────────────────────────────────
function startSyncLoop() {
  function tick() {
    const t = audio.currentTime;

    // Find active sentence
    let active = -1;
    for (let i = 0; i < state.sync.length; i++) {
      if (t >= state.sync[i].start && t < state.sync[i].end) {
        active = i;
        break;
      }
    }
    // Fallback: if past all sentences, highlight last
    if (active === -1 && state.sync.length > 0 && t >= state.sync[state.sync.length - 1].start) {
      active = state.sync.length - 1;
    }

    if (active !== state.activeSentIdx) {
      // Dehighlight old
      if (state.activeSentIdx >= 0) {
        const old = document.querySelector(`.sentence[data-idx="${state.activeSentIdx}"]`);
        if (old) old.classList.remove('active');
      }
      // Highlight new
      if (active >= 0) {
        const el = document.querySelector(`.sentence[data-idx="${active}"]`);
        if (el) {
          el.classList.add('active');
          scrollToSentence(el);
        }
      }
      state.activeSentIdx = active;
    }

    // Update progress bar
    if (!audio.paused && audio.duration) {
      document.getElementById('progress-bar').value = Math.floor(audio.currentTime);
      document.getElementById('time-current').textContent = fmtTime(audio.currentTime);
    }

    state.rafId = requestAnimationFrame(tick);
  }
  state.rafId = requestAnimationFrame(tick);
}

function scrollToSentence(el) {
  const wrap = document.getElementById('reader-wrap');
  const wrapRect  = wrap.getBoundingClientRect();
  const elRect    = el.getBoundingClientRect();
  const elCenter  = elRect.top + elRect.height / 2;
  const wrapCenter = wrapRect.top + wrapRect.height / 2;
  const offset    = elCenter - wrapCenter;
  wrap.scrollBy({ top: offset, behavior: 'smooth' });
}

function seekToSentence(idx) {
  if (!state.sync[idx]) return;
  audio.currentTime = state.sync[idx].start;
  if (audio.paused) {
    audio.play();
    document.getElementById('play-btn').textContent = '⏸';
  }
}

// ── AUDIO CONTROLS ─────────────────────────────────────────────
document.getElementById('play-btn').addEventListener('click', () => {
  if (audio.paused) {
    audio.play();
    document.getElementById('play-btn').textContent = '⏸';
    startSyncLoop();
  } else {
    audio.pause();
    document.getElementById('play-btn').textContent = '▶';
    cancelAnimationFrame(state.rafId);
  }
});

audio.addEventListener('ended', () => {
  document.getElementById('play-btn').textContent = '▶';
  cancelAnimationFrame(state.rafId);
  // Auto-advance to next chapter
  if (state.currentCh < state.totalChs) {
    showToast('Loading next chapter…');
    setTimeout(() => loadChapter(state.currentCh + 1), 800);
  }
});

document.getElementById('rw-btn').addEventListener('click', () => {
  audio.currentTime = Math.max(0, audio.currentTime - 15);
});
document.getElementById('ff-btn').addEventListener('click', () => {
  audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 15);
});

// Progress bar scrubbing
let scrubbing = false;
document.getElementById('progress-bar').addEventListener('mousedown', () => { scrubbing = true; });
document.getElementById('progress-bar').addEventListener('input', e => {
  document.getElementById('time-current').textContent = fmtTime(parseInt(e.target.value));
});
document.getElementById('progress-bar').addEventListener('change', e => {
  audio.currentTime = parseInt(e.target.value);
  scrubbing = false;
});

audio.addEventListener('timeupdate', () => {
  if (!scrubbing && audio.duration) {
    document.getElementById('progress-bar').value = Math.floor(audio.currentTime);
    document.getElementById('time-current').textContent = fmtTime(audio.currentTime);
  }
});

// Speed
document.querySelectorAll('.speed-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    audio.playbackRate = parseFloat(btn.dataset.speed);
  });
});

// Chapter nav
document.getElementById('prev-ch-btn').addEventListener('click', () => {
  if (state.currentCh > 1) loadChapter(state.currentCh - 1);
});
document.getElementById('next-ch-btn').addEventListener('click', () => {
  if (state.currentCh < state.totalChs) loadChapter(state.currentCh + 1);
});

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  switch(e.key) {
    case ' ':
      e.preventDefault();
      document.getElementById('play-btn').click();
      break;
    case 'ArrowLeft':
      audio.currentTime = Math.max(0, audio.currentTime - 15);
      break;
    case 'ArrowRight':
      audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 15);
      break;
    case 'ArrowUp':
      if (state.currentCh > 1) loadChapter(state.currentCh - 1);
      break;
    case 'ArrowDown':
      if (state.currentCh < state.totalChs) loadChapter(state.currentCh + 1);
      break;
  }
});

// Font size
let fontSize = 18;
document.getElementById('font-up').addEventListener('click', () => {
  fontSize = Math.min(28, fontSize + 1);
  document.documentElement.style.setProperty('--font-size', fontSize + 'px');
});
document.getElementById('font-down').addEventListener('click', () => {
  fontSize = Math.max(14, fontSize - 1);
  document.documentElement.style.setProperty('--font-size', fontSize + 'px');
});

// ── LIBRARY PANEL ──────────────────────────────────────────────
document.getElementById('library-btn').addEventListener('click', () => {
  document.getElementById('library-panel').classList.toggle('open');
});
document.getElementById('panel-close').addEventListener('click', () => {
  document.getElementById('library-panel').classList.remove('open');
});

// ── UTILS ──────────────────────────────────────────────────────
function fmtTime(sec) {
  if (!sec || isNaN(sec)) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ── INIT ───────────────────────────────────────────────────────
loadLibrary();
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gradient Reader — Flask server")
    parser.add_argument("--port",    type=int, default=5001)
    parser.add_argument("--host",    default="0.0.0.0",
                        help="Host to bind (0.0.0.0 for Tailscale access)")
    parser.add_argument("--library", default=None,
                        help="Override library root path (default: data/output/)")
    args = parser.parse_args()

    if args.library:
        LIBRARY_ROOT = Path(args.library)

    print(f"\n{'='*50}")
    print(f"  Gradient Reader")
    print(f"  http://{args.host}:{args.port}")
    print(f"  Library: {LIBRARY_ROOT}")
    print(f"{'='*50}\n")

    if not LIBRARY_ROOT.exists():
        print(f"  ⚠  Library root does not exist: {LIBRARY_ROOT}")
        print(f"  Run generate_sync.py first to create a book entry.\n")

    app.run(host=args.host, port=args.port, debug=False, threaded=True)