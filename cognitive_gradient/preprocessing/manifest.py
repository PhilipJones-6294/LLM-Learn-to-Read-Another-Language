import json
import logging
import os
from typing import Dict, List, Optional

from cognitive_gradient.pipeline.budget import calculate_budget, determine_stage

logger = logging.getLogger(__name__)


def manifest_exists(manifest_path: str) -> bool:
    return os.path.exists(manifest_path)


def load_manifest(manifest_path: str) -> Dict:
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_manifest(
    all_clauses: List[Dict],
    all_scenes: List[Dict],
    scene_summaries: List[Dict],
    config,
    novel_title: str = "Unknown",
) -> None:
    """
    Merge segmentation output with scene summaries, compute positions/budgets,
    populate local context windows, then write manifest.json to disk.
    """
    os.makedirs(os.path.dirname(os.path.abspath(config.MANIFEST_PATH)), exist_ok=True)

    # Index summaries by scene_id for O(1) lookup
    summary_index: Dict[str, Dict] = {s["scene_id"]: s for s in scene_summaries}

    total_clauses = len(all_clauses)
    if total_clauses == 0:
        raise ValueError("No clauses extracted — check input file and segmenter.")

    # Pass 1: compute position, budget, stage for every clause
    for global_idx, clause in enumerate(all_clauses):
        position = global_idx / max(total_clauses - 1, 1)
        token_count = len(clause["text"].split())
        clause["position"] = round(position, 6)
        clause["budget"] = calculate_budget(position, token_count, config)
        clause["stage"] = determine_stage(position, config)

    # Pass 2: populate local context windows
    wb = config.LOCAL_WINDOW_BEFORE
    wa = config.LOCAL_WINDOW_AFTER
    for global_idx, clause in enumerate(all_clauses):
        clause["local_before"] = [
            all_clauses[i]["text"]
            for i in range(max(0, global_idx - wb), global_idx)
        ]
        clause["local_after"] = [
            all_clauses[i]["text"]
            for i in range(global_idx + 1, min(total_clauses, global_idx + wa + 1))
        ]

    # Pass 3: merge scene summaries into scene dicts and build manifest structure
    manifest_scenes: List[Dict] = []
    for scene in all_scenes:
        sid = scene["scene_id"]
        summary = summary_index.get(sid, {})

        manifest_scenes.append(
            {
                "scene_id": sid,
                "chapter": scene["chapter"],
                "chapter_heading": scene.get("chapter_heading", ""),
                "stake": summary.get("stake", ""),
                "emotional_register": summary.get("emotional_register", "neutral"),
                "soft_anchors": summary.get("soft_anchors", []),
                "clauses": scene["clauses"],
            }
        )

    manifest: Dict = {
        "novel_title": novel_title,
        "total_clauses": total_clauses,
        "scenes": manifest_scenes,
    }

    with open(config.MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    logger.info(
        "Manifest written to %s (%d scenes, %d clauses)",
        config.MANIFEST_PATH,
        len(manifest_scenes),
        total_clauses,
    )
