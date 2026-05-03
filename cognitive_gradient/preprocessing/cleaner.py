import os
import re


def detect_format(path: str) -> str:
    return "epub" if path.lower().endswith(".epub") else "txt"


def clean(text: str, source_format: str = "txt") -> str:
    """
    Clean raw novel text.

    epub path runs a structural pre-pass first; both paths then share the
    artifact cleaner. Does NOT touch intentional stylistic choices:
    ellipsis chains, ALL-CAPS dialogue, backtick quotes, or em-dashes.
    """
    if source_format == "epub":
        text = _pre_clean_epub(text)
    return _clean_shared(text)


def _pre_clean_epub(text: str) -> str:
    """Normalise unicode and remove epub structural noise before shared clean."""
    text = text.replace("\xa0", " ")
    text = text.replace("—", " — ")   # em-dash — keep, just space it
    text = text.replace("–", " – ")   # en-dash
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\[\d+\]", "", text)          # footnote markers [1]
    text = re.sub(
        r"(?m)^\s*(Contents|Next Chapter|Previous Chapter|Back to top)\s*$",
        "",
        text,
    )
    return text


def _clean_shared(text: str) -> str:
    """OCR and formatting artifacts common to scanned .txt files."""
    # CRLF normalisation
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Hard hyphen line-wrap: "talk-\ning" → "talking"
    text = re.sub(r"(\w)-\n(\w)", lambda m: m.group(1) + m.group(2), text)

    # Soft mid-word break discriminator:
    # Fires when char before \n is a letter preceded by another letter
    # AND the suffix after \n starts with a lowercase letter ≤ 4 chars before a separator.
    # "Un\ncle " → "Uncle "; "He\nwas" still fires but is rare enough at novel scale.
    text = re.sub(
        r"(?<=[a-zA-Z][a-zA-Z])\n(?=[a-z]{1,4}(?:[\s.!?,;:]|$))",
        "",
        text,
    )

    # Stray page numbers — standalone 1-4 digit lines
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", "", text)

    # Collapse excess blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
