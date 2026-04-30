"""
Cognitive Gradient Engine — entry point.

Usage:
    python -m cognitive_gradient.main
    python -m cognitive_gradient.main --force-preprocess
    python -m cognitive_gradient.main --chapter 1          # single-chapter test run
    python -m cognitive_gradient.main --input path/to/book.txt
"""

import argparse
import logging
import os
import sys

from tqdm import tqdm

import cognitive_gradient.config as config
from cognitive_gradient.pipeline.stitcher import stitch
from cognitive_gradient.pipeline.translator import process_clause
from cognitive_gradient.preprocessing.loader import load_novel
from cognitive_gradient.preprocessing.manifest import (
    build_manifest,
    load_manifest,
    manifest_exists,
)
from cognitive_gradient.preprocessing.segmenter import segment
from cognitive_gradient.preprocessing.summarizer import summarize_scenes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cognitive Gradient Engine")
    parser.add_argument(
        "--force-preprocess",
        action="store_true",
        help="Re-run preprocessing even if manifest already exists.",
    )
    parser.add_argument(
        "--chapter",
        type=int,
        default=None,
        metavar="N",
        help="Process only chapter N (useful for single-chapter validation).",
    )
    parser.add_argument(
        "--input",
        default=None,
        metavar="PATH",
        help="Override INPUT_PATH from config.",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="Override OUTPUT_PATH from config.",
    )
    return parser.parse_args()


def run(
    force_preprocess: bool = False,
    chapter_filter: int | None = None,
    input_path: str | None = None,
    output_path: str | None = None,
) -> None:
    in_path = input_path or config.INPUT_PATH
    out_path = output_path or config.OUTPUT_PATH

    # ── Preprocessing ──────────────────────────────────────────────────────────
    if force_preprocess or not manifest_exists(config.MANIFEST_PATH):
        logger.info("Running preprocessing on %s", in_path)
        text = load_novel(in_path)

        novel_title = os.path.splitext(os.path.basename(in_path))[0]

        logger.info("Segmenting clauses and scenes…")
        all_clauses, all_scenes = segment(text, config)
        logger.info(
            "Segmentation complete: %d clauses across %d scenes",
            len(all_clauses),
            len(all_scenes),
        )

        logger.info("Summarising scenes…")
        scene_summaries = summarize_scenes(all_scenes, config)

        logger.info("Building manifest…")
        build_manifest(all_clauses, all_scenes, scene_summaries, config, novel_title=novel_title)
    else:
        logger.info("Using cached manifest at %s", config.MANIFEST_PATH)

    # ── Main pipeline ──────────────────────────────────────────────────────────
    manifest = load_manifest(config.MANIFEST_PATH)

    scenes_to_process = manifest["scenes"]
    if chapter_filter is not None:
        scenes_to_process = [s for s in scenes_to_process if s["chapter"] == chapter_filter]
        if not scenes_to_process:
            logger.error("No scenes found for chapter %d — check chapter numbering.", chapter_filter)
            sys.exit(1)
        logger.info("Chapter filter active: processing chapter %d only", chapter_filter)

    output_clauses: list[str] = []
    total_clauses = sum(len(s["clauses"]) for s in scenes_to_process)

    with tqdm(total=total_clauses, desc="Gradient pass", unit="clause") as pbar:
        for scene in scenes_to_process:
            for clause in scene["clauses"]:
                gradient = process_clause(clause, scene, config)
                output_clauses.append(gradient)
                pbar.update(1)

    # ── Stitch and write output ────────────────────────────────────────────────
    # When a chapter filter is active, build a partial manifest for the stitcher
    active_manifest = manifest if chapter_filter is None else {
        **manifest,
        "scenes": scenes_to_process,
    }
    stitch(output_clauses, active_manifest, out_path)
    logger.info("Done. Output written to %s", out_path)


if __name__ == "__main__":
    args = _parse_args()
    run(
        force_preprocess=args.force_preprocess,
        chapter_filter=args.chapter,
        input_path=args.input,
        output_path=args.output,
    )
