#!/usr/bin/env python3
"""
generate_sync.py — Reader Library Preprocessor

Standalone script. No cognitive_gradient imports.
Lives at: cognitive_gradient/generate_sync.py
Project root is resolved as Path(__file__).parent.parent so all default
paths (data/input, data/output) are relative to the repo root regardless
of where the script is invoked from.

Takes a gradient text file (already produced by the pipeline) and a raw
input text file (for chapter boundary detection), then for each chapter:
  1. Splits the gradient text by chapter
  2. Runs edge-tts to produce audio.mp3 + word-timing .vtt
  3. Aligns sentences to VTT word timestamps → sync.json
  4. Writes the reader library folder

Usage (from project root):
    python cognitive_gradient/generate_sync.py \\
        --gradient data/output/hp1_gradient.txt \\
        --raw      data/input/harry_potter_1.txt \\
        --name     hp1 \\
        --title    "Harry Potter and the Philosopher's Stone" \\
        --author   "J.K. Rowling" \\
        --voice    fr-FR-DeniseNeural \\
        --rate     "-25%"

Or as a module:
    python -m cognitive_gradient.generate_sync \\
        --gradient data/output/hp1_gradient.txt \\
        --raw      data/input/harry_potter_1.txt \\
        --name     hp1 \\
        --title    "Harry Potter and the Philosopher's Stone"

Resume support: if a chapter folder already contains audio.mp3 and sync.json,
that chapter is skipped unless --force is passed.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Optional

# ─────────────────────────────────────────────────────────────────
# PROJECT ROOT  (cognitive_gradient/ → parent → repo root)
# Works correctly whether run as:
#   python cognitive_gradient/generate_sync.py   (from repo root)
#   python -m cognitive_gradient.generate_sync   (as module)
# ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────
# CHAPTER DETECTION  (self-contained, no spaCy)
# ─────────────────────────────────────────────────────────────────

CHAPTER_PATTERN = re.compile(
    r"^(chapter\s+\w+|chapter\s+\d+|\d+\.\s+\w+|[IVXLCDM]+\.\s+\w+)",
    re.IGNORECASE,
)


def detect_chapters(text: str) -> List[Tuple[str, str]]:
    """
    Split text into (heading, body) pairs.
    Returns at least one entry.
    """
    lines = text.split("\n")
    chapters: List[Tuple[str, str]] = []
    current_heading = ""
    current_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and CHAPTER_PATTERN.match(stripped):
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    chapters.append((current_heading, body))
            current_heading = stripped
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            chapters.append((current_heading, body))

    chapters = [(h, b) for h, b in chapters if h.strip()]
    return chapters if chapters else [("", text)]


# ─────────────────────────────────────────────────────────────────
# SENTENCE SPLITTING  (regex, no NLP dependency)
# ─────────────────────────────────────────────────────────────────

# Sentence boundary: period/!/? followed by space + capital, or end of string.
# Handles common abbreviations to reduce false splits.
_ABBREV = re.compile(
    r"\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|al|St|Mt|Vol|No|pp|Fig)\.$",
    re.IGNORECASE,
)

def split_sentences(text: str) -> List[str]:
    """Split a paragraph or block of text into sentences."""
    # Normalise whitespace
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    # Split on sentence-ending punctuation followed by space + uppercase
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', text)

    sentences: List[str] = []
    buffer = ""
    for part in raw:
        candidate = (buffer + " " + part).strip() if buffer else part
        # If the candidate ends with an abbreviation, keep buffering
        if _ABBREV.search(candidate.rstrip()):
            buffer = candidate
        else:
            if candidate:
                sentences.append(candidate)
            buffer = ""
    if buffer:
        sentences.append(buffer)

    return [s for s in sentences if s.strip()]


def chapter_sentences(chapter_body: str) -> List[str]:
    """Return all sentences from a chapter body, in order."""
    # Handle both double-newline and single-newline paragraph breaks
    paragraphs = re.split(r"\n+", chapter_body)
    sentences: List[str] = []
    for para in paragraphs:
        para = para.strip()
        if para:
            sentences.extend(split_sentences(para))
    return sentences


# ─────────────────────────────────────────────────────────────────
# SRT PARSING  (edge-tts SubMaker.get_srt() produces SRT, not VTT)
# ─────────────────────────────────────────────────────────────────

_SRT_TIMESTAMP = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


def _ts_to_sec(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(srt_path: Path) -> List[Dict]:
    """
    Parse an SRT file (from edge-tts SubMaker.get_srt()) into word timing dicts:
        {"word": str, "start": float, "end": float}
    """
    text = srt_path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\n+", text.strip())
    words: List[Dict] = []

    for block in blocks:
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        ts_line = None
        text_lines = []
        for line in lines:
            if _SRT_TIMESTAMP.search(line):
                ts_line = line
            elif not re.match(r"^\d+$", line):  # skip block number lines
                text_lines.append(line)

        if ts_line is None or not text_lines:
            continue

        m = _SRT_TIMESTAMP.search(ts_line)
        if not m:
            continue

        start = _ts_to_sec(m.group(1), m.group(2), m.group(3), m.group(4))
        end   = _ts_to_sec(m.group(5), m.group(6), m.group(7), m.group(8))
        word  = " ".join(text_lines).strip()

        if word:
            words.append({"word": word, "start": start, "end": end})

    return words


# ─────────────────────────────────────────────────────────────────
# SENTENCE → TIMESTAMP ALIGNMENT
# ─────────────────────────────────────────────────────────────────

def _normalise(s: str) -> str:
    """Strip punctuation and lowercase for fuzzy word matching."""
    return re.sub(r"[^a-z0-9\s]", "", s.lower()).strip()


def get_mp3_duration(mp3_path: Path) -> float:
    """Get MP3 duration in seconds. Tries mutagen, falls back to file-size estimate."""
    try:
        from mutagen.mp3 import MP3
        return MP3(str(mp3_path)).info.length
    except Exception:
        pass
    # Fallback: ~16KB per second at 128kbps
    size = mp3_path.stat().st_size if mp3_path.exists() else 0
    return size / 16000.0


def align_sentences(sentences: List[str], word_timings: List[Dict],
                    audio_path: Path = None) -> List[Dict]:
    """
    Align each sentence to a time range using the word timing list.
    If no word timings, distribute proportionally across actual audio duration.

    Returns list of:
        {"index": int, "text": str, "start": float, "end": float}
    """
    if not word_timings:
        # Get actual duration for proportional distribution
        total_duration = get_mp3_duration(audio_path) if audio_path else 0.0
        word_counts = [max(1, len(s.split())) for s in sentences]
        total_words = sum(word_counts)
        result = []
        t = 0.0
        for i, s in enumerate(sentences):
            if total_duration > 0:
                duration = (word_counts[i] / total_words) * total_duration
            else:
                duration = word_counts[i] * 0.5  # 120 wpm fallback
            result.append({"index": i, "text": s, "start": round(t, 3),
                           "end": round(t + duration, 3)})
            t += duration
        return result

    # Flatten word_timings into a simple searchable list
    wt_words = [_normalise(w["word"]) for w in word_timings]
    wt_ptr = 0
    result = []

    for sent_idx, sentence in enumerate(sentences):
        sent_tokens = _normalise(sentence).split()
        if not sent_tokens:
            # Empty sentence — use last known time
            last_end = result[-1]["end"] if result else 0.0
            result.append({"index": sent_idx, "text": sentence, "start": last_end, "end": last_end})
            continue

        # Find first token match from current pointer
        first_token = sent_tokens[0]
        match_start = None
        search_limit = min(wt_ptr + 50, len(wt_words))  # lookahead window

        for i in range(wt_ptr, search_limit):
            if wt_words[i] == first_token or first_token in wt_words[i] or wt_words[i] in first_token:
                match_start = i
                break

        # Fallback: broader search if strict match fails
        if match_start is None:
            for i in range(wt_ptr, min(wt_ptr + 120, len(wt_words))):
                if any(t in wt_words[i] for t in sent_tokens[:3] if len(t) > 3):
                    match_start = i
                    break

        if match_start is None:
            # Can't find — use last known time + estimate
            last_end = result[-1]["end"] if result else 0.0
            duration = len(sent_tokens) * 0.4
            result.append({
                "index": sent_idx,
                "text": sentence,
                "start": last_end,
                "end": last_end + duration,
            })
            continue

        # Walk forward to find where this sentence ends
        # Try to match the last token
        last_token = sent_tokens[-1]
        match_end = match_start
        search_end = min(match_start + len(sent_tokens) + 30, len(wt_words))

        for i in range(search_end - 1, match_start - 1, -1):
            if wt_words[i] == last_token or last_token in wt_words[i]:
                match_end = i
                break

        # Ensure end >= start
        if match_end < match_start:
            match_end = min(match_start + len(sent_tokens) - 1, len(wt_words) - 1)

        result.append({
            "index": sent_idx,
            "text": sentence,
            "start": word_timings[match_start]["start"],
            "end":   word_timings[match_end]["end"],
        })

        wt_ptr = match_end + 1
        if wt_ptr >= len(wt_words):
            # Ran out of timings — estimate the rest
            for remaining_idx in range(sent_idx + 1, len(sentences)):
                last_end = result[-1]["end"]
                wc = len(sentences[remaining_idx].split())
                result.append({
                    "index": remaining_idx,
                    "text": sentences[remaining_idx],
                    "start": last_end,
                    "end": last_end + wc * 0.4,
                })
            break

    return result


# ─────────────────────────────────────────────────────────────────
# EDGE-TTS
# ─────────────────────────────────────────────────────────────────

async def _run_edge_tts(
    text: str,
    voice: str,
    rate: str,
    mp3_path: Path,
    srt_path: Path,
) -> None:
    """Run edge-tts async to produce mp3 + word-cue srt."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    submaker = edge_tts.SubMaker()

    with open(mp3_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    srt_path.write_text(submaker.get_srt(), encoding="utf-8")


def run_edge_tts(text: str, voice: str, rate: str, mp3_path: Path, srt_path: Path) -> None:
    asyncio.run(_run_edge_tts(text, voice, rate, mp3_path, srt_path))


# ─────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────

def process_chapter(
    ch_idx: int,
    heading: str,
    gradient_body: str,
    book_dir: Path,
    voice: str,
    rate: str,
    force: bool,
) -> Dict:
    """
    Process one chapter:
      1. Write text.txt
      2. Run edge-tts → audio.mp3 + raw.vtt
      3. Parse VTT → align sentences → write sync.json
      4. Return chapter metadata dict
    """
    ch_label = f"ch{ch_idx:02d}"
    ch_dir = book_dir / ch_label
    ch_dir.mkdir(parents=True, exist_ok=True)

    text_path  = ch_dir / "text.txt"
    audio_path = ch_dir / "audio.mp3"
    srt_path   = ch_dir / "raw.srt"
    sync_path  = ch_dir / "sync.json"

    # Write gradient text
    text_path.write_text(gradient_body, encoding="utf-8")

    # Resume check
    if not force and audio_path.exists() and sync_path.exists():
        print(f"  ✓ {ch_label} already done — skipping (use --force to redo)")
        existing_sync = json.loads(sync_path.read_text())
        return {
            "index": ch_idx,
            "label": ch_label,
            "heading": heading,
            "sentence_count": len(existing_sync),
            "audio_duration": existing_sync[-1]["end"] if existing_sync else 0,
        }

    sentences = chapter_sentences(gradient_body)
    print(f"  → {ch_label}: {len(sentences)} sentences — generating audio...")

    if not sentences:
        print(f"  ⚠  {ch_label}: no sentences found, skipping")
        return {"index": ch_idx, "label": ch_label, "heading": heading,
                "sentence_count": 0, "audio_duration": 0}

    # Run edge-tts
    run_edge_tts(gradient_body, voice, rate, audio_path, srt_path)
    print(f"  → {ch_label}: audio done ({audio_path.stat().st_size // 1024} KB)")

    # Parse SRT
    word_timings: List[Dict] = []
    if srt_path.exists() and srt_path.stat().st_size > 0:
        word_timings = parse_srt(srt_path)
        print(f"  → {ch_label}: {len(word_timings)} word timings parsed")
    else:
        print(f"  ⚠  {ch_label}: no SRT produced — using estimated timings")

    # Align sentences → sync
    aligned = align_sentences(sentences, word_timings, audio_path=audio_path)
    sync_path.write_text(json.dumps(aligned, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {ch_label}: sync.json written ({len(aligned)} entries)")

    # Clean up raw srt
    if srt_path.exists():
        srt_path.unlink()

    duration = aligned[-1]["end"] if aligned else 0.0
    return {
        "index": ch_idx,
        "label": ch_label,
        "heading": heading,
        "sentence_count": len(aligned),
        "audio_duration": round(duration, 2),
    }


def run(
    gradient_path: Path,
    raw_path: Path,
    book_name: str,
    title: str,
    author: str,
    voice: str,
    rate: str,
    output_root: Path,
    force: bool,
    chapter_filter: Optional[int],
) -> None:

    # Read files
    print(f"\nReading gradient text: {gradient_path}")
    gradient_text = gradient_path.read_text(encoding="utf-8", errors="replace")

    print(f"Reading raw text for chapter detection: {raw_path}")
    raw_text = raw_path.read_text(encoding="utf-8", errors="replace")

    # Detect chapters from raw text (clean boundaries)
    raw_chapters = detect_chapters(raw_text)
    gradient_chapters = detect_chapters(gradient_text)

    print(f"Detected {len(raw_chapters)} chapters in raw text")
    print(f"Detected {len(gradient_chapters)} chapters in gradient text")

    # Use raw chapter count as ground truth; pair with gradient bodies
    n_chapters = min(len(raw_chapters), len(gradient_chapters))
    if len(raw_chapters) != len(gradient_chapters):
        print(f"⚠  Chapter count mismatch — using first {n_chapters} chapters")

    # Build output directory
    book_dir = output_root / book_name
    book_dir.mkdir(parents=True, exist_ok=True)

    # Process chapters
    chapter_meta = []
    for i in range(n_chapters):
        ch_num = i + 1  # 1-indexed

        if chapter_filter is not None and ch_num != chapter_filter:
            continue

        raw_heading, _   = raw_chapters[i]
        _, gradient_body = gradient_chapters[i]

        heading = raw_heading or f"Chapter {ch_num}"
        print(f"\n[Chapter {ch_num}/{n_chapters}] {heading}")

        meta = process_chapter(
            ch_idx=ch_num,
            heading=heading,
            gradient_body=gradient_body,
            book_dir=book_dir,
            voice=voice,
            rate=rate,
            force=force,
        )
        chapter_meta.append(meta)

    # Write meta.json
    meta_path = book_dir / "meta.json"
    meta = {
        "name":       book_name,
        "title":      title,
        "author":     author,
        "voice":      voice,
        "rate":       rate,
        "chapters":   chapter_meta,
        "generated":  datetime.utcnow().isoformat() + "Z",
        "total_chapters": n_chapters,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ meta.json written: {meta_path}")
    print(f"✓ Library entry ready: {book_dir}")


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Generate reader library entry from gradient text + raw novel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--gradient", required=True, metavar="PATH",
                        help="Path to gradient text file (pipeline output)")
    parser.add_argument("--raw",      required=True, metavar="PATH",
                        help="Path to raw input novel (for chapter detection)")
    parser.add_argument("--name",     required=True, metavar="NAME",
                        help="Short book identifier, e.g. hp1")
    parser.add_argument("--title",    default="Untitled", metavar="TITLE")
    parser.add_argument("--author",   default="Unknown",  metavar="AUTHOR")
    parser.add_argument("--voice",    default="fr-FR-DeniseNeural", metavar="VOICE")
    parser.add_argument("--rate",     default="-25%",     metavar="RATE",
                        help="edge-tts rate modifier, e.g. -25%%")
    parser.add_argument("--output",   default=None, metavar="DIR",
                        help="Root output directory (default: <project_root>/data/output)")
    parser.add_argument("--chapter",  type=int, default=None, metavar="N",
                        help="Process only chapter N (1-indexed)")
    parser.add_argument("--force",    action="store_true",
                        help="Re-process chapters even if already done")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    # Resolve paths relative to project root so the script works correctly
    # whether invoked from the repo root, a subdirectory, or as a module.
    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    gradient_path = _resolve(args.gradient)
    raw_path      = _resolve(args.raw)
    output_root   = _resolve(args.output) if args.output else (PROJECT_ROOT / "data" / "output")

    if not gradient_path.exists():
        print(f"ERROR: gradient file not found: {gradient_path}", file=sys.stderr)
        sys.exit(1)
    if not raw_path.exists():
        print(f"ERROR: raw input file not found: {raw_path}", file=sys.stderr)
        sys.exit(1)

    try:
        import edge_tts
    except ImportError:
        print("ERROR: edge-tts not installed. Run: pip install edge-tts", file=sys.stderr)
        sys.exit(1)

    run(
        gradient_path  = gradient_path,
        raw_path       = raw_path,
        book_name      = args.name,
        title          = args.title,
        author         = args.author,
        voice          = args.voice,
        rate           = args.rate,
        output_root    = output_root,
        force          = args.force,
        chapter_filter = args.chapter,
    )