"""
text_to_mp3.py — Convert gradient French/English text to MP3 using Edge TTS.

Strategy: Use a French neural voice for ALL text (both English and French words).
This gives English words a natural French accent, which is ideal for immersive
language learning — the learner hears everything through a French speaker's mouth.

Recommended voices:
    fr-FR-DeniseNeural  — Female, clear and natural (default)
    fr-FR-HenriNeural   — Male, warm and expressive
    fr-FR-EloiseNeural  — Female, softer tone
    fr-BE-CharlineNeural — Belgian French accent variation

Usage:
    python text_to_mp3.py --input data/output/chapter_01.txt
    python text_to_mp3.py --input data/output/chapter_01.txt --output audio/ch01.mp3
    python text_to_mp3.py --input chapter_01.txt --voice fr-FR-HenriNeural
    python text_to_mp3.py --text "Harry tried to argue back, mais ses mots were lost."
    python text_to_mp3.py --list-voices --lang fr
"""

import argparse
import asyncio
import os
import sys
import edge_tts


# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_VOICE  = "fr-FR-DeniseNeural"  # French female — reads all text with French accent
DEFAULT_RATE   = "-20%"                # Slower — better for language learning
DEFAULT_VOLUME = "+0%"


# ── Core TTS ──────────────────────────────────────────────────────────────────

async def text_to_mp3(
    text: str,
    output_path: str,
    voice: str,
    rate: str,
    volume: str,
) -> None:
    """Stream Edge TTS audio to an MP3 file."""
    print(f"\nVoice:       {voice}")
    print(f"Rate:        {rate}")
    print(f"Characters:  {len(text):,}")
    print(f"Output:      {output_path}")
    print("Converting... ", end="", flush=True)

    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)

    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])

    size_mb = os.path.getsize(output_path) / 1_048_576
    print(f"done  ({size_mb:.1f} MB)\n")


# ── Voice listing ─────────────────────────────────────────────────────────────

async def list_voices(lang_filter: str = None) -> None:
    voices = await edge_tts.list_voices()
    filtered = [
        v for v in voices
        if not lang_filter or v["ShortName"].lower().startswith(lang_filter.lower())
    ]
    for v in sorted(filtered, key=lambda x: x["ShortName"]):
        gender = v.get("Gender", "")
        print(f"  {v['ShortName']:<38} {gender}")
    print(f"\n  {len(filtered)} voice(s) shown.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert gradient French/English text to MP3 (French-accented voice)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input",  "-i", metavar="PATH",
                        help="Input text file (reads stdin if omitted)")
    parser.add_argument("--output", "-o", metavar="PATH",
                        help="Output MP3 path (auto-named from input if omitted)")
    parser.add_argument("--text",   "-t", metavar="TEXT",
                        help="Pass text inline instead of a file")
    parser.add_argument("--voice",  "-v", default=DEFAULT_VOICE,
                        help=f"Edge TTS voice name (default: {DEFAULT_VOICE})")
    parser.add_argument("--rate", default=DEFAULT_RATE,
                        help=f"Speech rate adjustment (default: {DEFAULT_RATE})")
    parser.add_argument("--volume", default=DEFAULT_VOLUME,
                        help=f"Volume adjustment (default: {DEFAULT_VOLUME})")
    parser.add_argument("--list-voices", action="store_true",
                        help="List available voices and exit")
    parser.add_argument("--lang", default=None,
                        help="Filter --list-voices by prefix e.g. fr or fr-FR")
    args = parser.parse_args()

    # ── List voices mode ──────────────────────────────────────────────────────
    if args.list_voices:
        prefix = args.lang or "fr"
        print(f"\nVoices matching '{prefix}':\n")
        asyncio.run(list_voices(prefix))
        return

    # ── Gather text ───────────────────────────────────────────────────────────
    if args.text:
        text = args.text.strip()
        stem = "inline"
    elif args.input:
        if not os.path.exists(args.input):
            print(f"Error: file not found — {args.input}", file=sys.stderr)
            sys.exit(1)
        with open(args.input, encoding="utf-8") as f:
            text = f.read().strip()
        stem = os.path.splitext(os.path.basename(args.input))[0]
    else:
        print("Reading from stdin (Ctrl+D to finish)…")
        text = sys.stdin.read().strip()
        stem = "stdin_output"

    if not text:
        print("Error: no text to convert.", file=sys.stderr)
        sys.exit(1)

    # ── Resolve output path ───────────────────────────────────────────────────
    output_path = args.output or f"{stem}.mp3"
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # ── Convert ───────────────────────────────────────────────────────────────
    asyncio.run(text_to_mp3(text, output_path, args.voice, args.rate, args.volume))


if __name__ == "__main__":
    main()