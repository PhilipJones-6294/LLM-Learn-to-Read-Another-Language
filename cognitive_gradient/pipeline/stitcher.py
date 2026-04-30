import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)


def stitch(output_clauses: List[str], manifest: Dict, output_path: str) -> None:
    """
    Reassemble gradient clauses into the final novel file.

    - Paragraph structure is reconstructed using paragraph_break_before flags.
    - Chapter headings are emitted in English whenever the chapter number changes.
    - Output is UTF-8 encoded.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    parts: List[str] = []       # Each entry becomes a paragraph block
    current_para: List[str] = []
    clause_idx = 0
    prev_chapter: int = -1

    def flush_para() -> None:
        if current_para:
            parts.append(" ".join(current_para))
            current_para.clear()

    for scene in manifest["scenes"]:
        chapter = scene.get("chapter", 0)

        # Emit chapter heading when entering a new chapter
        if chapter != prev_chapter:
            flush_para()
            heading = scene.get("chapter_heading", "").strip()
            if heading:
                parts.append(heading)
            prev_chapter = chapter

        for clause in scene["clauses"]:
            gradient_text = (
                output_clauses[clause_idx]
                if clause_idx < len(output_clauses)
                else clause["text"]
            )
            clause_idx += 1

            if clause.get("paragraph_break_before", False) and current_para:
                flush_para()

            if gradient_text:
                current_para.append(gradient_text)

    flush_para()

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(parts))

    logger.info(
        "Stitcher wrote %d paragraphs / blocks to %s", len(parts), output_path
    )
