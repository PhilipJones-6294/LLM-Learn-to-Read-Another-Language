"""
Cognitive Gradient Engine — entry point.

Usage:
    python -m cognitive_gradient.main
    python -m cognitive_gradient.main --force-preprocess
    python -m cognitive_gradient.main --chapter 1          # single-chapter test run
    python -m cognitive_gradient.main --input path/to/book.txt
    python -m cognitive_gradient.main --input book.epub --output out.txt
"""

import argparse
import logging
import os
import sys
from typing import Dict, List, Optional

from tqdm import tqdm

import cognitive_gradient.config as config
from cognitive_gradient.pipeline.budget import assign_positions, stage_for_cluster
from cognitive_gradient.pipeline.clusterer import cluster_clauses
from cognitive_gradient.pipeline.ledger import Ledger
from cognitive_gradient.pipeline.stitcher import stitch
from cognitive_gradient.pipeline.translator import (
    process_clause,
    process_clause_with_ledger,
    translate_canonical,
)
from cognitive_gradient.preprocessing.cleaner import clean, detect_format
from cognitive_gradient.preprocessing.fragment_consolidator import consolidate_fragments
from cognitive_gradient.preprocessing.loader import load_novel
from cognitive_gradient.preprocessing.manifest import (
    build_manifest,
    load_manifest,
    manifest_exists,
)
from cognitive_gradient.preprocessing.ngram_analyzer import (
    analyse as ngram_analyse,
    priority_phrases,
    save as save_phrases,
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
    parser.add_argument("--input", default=None, metavar="PATH")
    parser.add_argument("--output", default=None, metavar="PATH")
    return parser.parse_args()


def _build_scene_lookup(all_scenes: List[Dict], summaries: List[Dict]) -> Dict[str, Dict]:
    """Merge segmentation scenes with LLM summaries into a keyed lookup."""
    summary_map = {s["scene_id"]: s for s in summaries}
    lookup: Dict[str, Dict] = {}
    for scene in all_scenes:
        sid = scene["scene_id"]
        summary = summary_map.get(sid, {})
        lookup[sid] = {
            **scene,
            "stake": summary.get("stake", ""),
            "emotional_register": summary.get("emotional_register", "neutral"),
            "soft_anchors": summary.get("soft_anchors", []),
        }
    return lookup


def run(
    force_preprocess: bool = False,
    chapter_filter: Optional[int] = None,
    input_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> None:
    in_path = input_path or config.INPUT_PATH
    out_path = output_path or config.OUTPUT_PATH

    # ── Ingest & Clean ──────────────────────────────────────────────────────────
    logger.info("Loading %s", in_path)
    raw = load_novel(in_path)
    source_format = detect_format(in_path)
    text = clean(raw, source_format=source_format)

    novel_title = os.path.splitext(os.path.basename(in_path))[0]

    # ── N-gram Frequency Analysis ───────────────────────────────────────────────
    logger.info("Analysing n-gram frequencies…")
    phrase_map = ngram_analyse(text, config)
    save_phrases(phrase_map, config.PHRASE_FREQ_PATH)
    top_phrases = priority_phrases(phrase_map, top_k=config.PHRASE_CONTEXT_TOP_K)
    logger.info("Top priority phrase: %r", top_phrases[0] if top_phrases else "—")

    # ── Preprocessing (cached) ──────────────────────────────────────────────────
    if force_preprocess or not manifest_exists(config.MANIFEST_PATH):
        logger.info("Segmenting clauses and scenes…")
        all_clauses, all_scenes = segment(text, config)
        logger.info(
            "Raw segmentation: %d clauses across %d scenes",
            len(all_clauses),
            len(all_scenes),
        )

        logger.info("Consolidating fragments (min_tokens=%d)…", config.MIN_CLUSTER_TOKENS)
        all_clauses = consolidate_fragments(all_clauses, min_tokens=config.MIN_CLUSTER_TOKENS)
        logger.info("After consolidation: %d clauses", len(all_clauses))

        # Assign positions now so clustering can use them
        assign_positions(all_clauses, config)

        logger.info("Summarising scenes…")
        summaries = summarize_scenes(all_scenes, config)

        # ── Pass 1: Frequency-First Ledger Build ────────────────────────────────
        ledger = Ledger(config.LEDGER_PATH)
        logger.info("Clustering clauses for frequency-first ledger build…")
        clusters = cluster_clauses(all_clauses, config)
        clusters_ranked = sorted(clusters, key=lambda c: -c["total_occurrences"])
        logger.info(
            "%d clusters from %d clauses (top cluster: %dx '%s')",
            len(clusters_ranked),
            len(all_clauses),
            clusters_ranked[0]["total_occurrences"] if clusters_ranked else 0,
            clusters_ranked[0]["canonical"][:40] if clusters_ranked else "",
        )

        scene_lookup = _build_scene_lookup(all_scenes, summaries)

        for cluster in tqdm(clusters_ranked, desc="Pass 1 — ledger build", unit="cluster"):
            if ledger.lookup(cluster["canonical"]):
                continue  # resume support — already translated
            result = translate_canonical(cluster, scene_lookup, config)
            ledger.write(cluster["canonical"], result, cluster)

        ledger.close()

        logger.info("Building manifest…")
        build_manifest(
            all_clauses, all_scenes, summaries, config,
            novel_title=novel_title, priority_phrases=top_phrases,
        )
    else:
        logger.info("Using cached manifest at %s", config.MANIFEST_PATH)

    # ── Pass 2: Full Novel Translation (novel order) ────────────────────────────
    manifest = load_manifest(config.MANIFEST_PATH)
    ledger = Ledger(config.LEDGER_PATH)

    scenes_to_process = manifest["scenes"]
    if chapter_filter is not None:
        scenes_to_process = [s for s in scenes_to_process if s["chapter"] == chapter_filter]
        if not scenes_to_process:
            logger.error("No scenes found for chapter %d.", chapter_filter)
            sys.exit(1)
        logger.info("Chapter filter active: chapter %d only", chapter_filter)

    output_clauses: List[str] = []
    total_clauses = sum(len(s["clauses"]) for s in scenes_to_process)

    with tqdm(total=total_clauses, desc="Pass 2 — novel translation", unit="clause") as pbar:
        for scene in scenes_to_process:
            for clause in scene["clauses"]:
                gradient = process_clause_with_ledger(clause, scene, ledger, config)
                output_clauses.append(gradient)
                pbar.update(1)

    ledger.close()

    # ── Stitch ──────────────────────────────────────────────────────────────────
    active_manifest = manifest if chapter_filter is None else {**manifest, "scenes": scenes_to_process}
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
