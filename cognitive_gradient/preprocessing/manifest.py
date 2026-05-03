import json
import logging
import os
from collections import defaultdict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def manifest_exists(manifest_path: str) -> bool:
    return os.path.exists(manifest_path)


def load_manifest(manifest_path: str) -> Dict:
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_scene_id(clause_id: str) -> str:
    """Extract scene_id from clause_id — format: ch01_sc000_cl000007 → ch01_sc000."""
    idx = clause_id.rfind("_cl")
    return clause_id[:idx] if idx != -1 else clause_id


def build_manifest(
    all_clauses: List[Dict],
    all_scenes: List[Dict],
    scene_summaries: List[Dict],
    config,
    novel_title: str = "Unknown",
    priority_phrases: Optional[List[str]] = None,
) -> None:
    """
    Build manifest.json from the consolidated clause list.

    all_clauses must have position/budget/stage already set (via assign_positions).
    all_scenes is used only for metadata (scene order, chapter, heading).
    Clauses are grouped into scenes using their scene_id field.
    priority_phrases are stamped onto each clause so the translator prompt knows
    which high-frequency targets appear in that clause.
    """
    os.makedirs(os.path.dirname(os.path.abspath(config.MANIFEST_PATH)), exist_ok=True)

    total_clauses = len(all_clauses)
    if total_clauses == 0:
        raise ValueError("No clauses extracted — check input file and segmenter.")

    # Positions/budgets/stages are assumed pre-assigned by assign_positions().
    # Populate local context windows.
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

        # Stamp priority phrases that appear in this clause
        if priority_phrases:
            clause_lower = clause["text"].lower()
            clause["priority_phrases"] = [
                p for p in priority_phrases if p in clause_lower
            ]
        else:
            clause["priority_phrases"] = []

    # Group consolidated clauses by scene_id (preserving order)
    scene_clause_map: Dict[str, List[Dict]] = defaultdict(list)
    for clause in all_clauses:
        sid = clause.get("scene_id") or _extract_scene_id(clause["clause_id"])
        scene_clause_map[sid].append(clause)

    # Index scene metadata and summaries
    scene_meta = {s["scene_id"]: s for s in all_scenes}
    summary_index = {s["scene_id"]: s for s in scene_summaries}

    # Build manifest scenes in original scene order
    manifest_scenes: List[Dict] = []
    for scene in all_scenes:
        sid = scene["scene_id"]
        meta = scene_meta.get(sid, scene)
        summary = summary_index.get(sid, {})

        manifest_scenes.append(
            {
                "scene_id": sid,
                "chapter": meta.get("chapter", 0),
                "chapter_heading": meta.get("chapter_heading", ""),
                "stake": summary.get("stake", ""),
                "emotional_register": summary.get("emotional_register", "neutral"),
                "soft_anchors": summary.get("soft_anchors", []),
                "clauses": scene_clause_map.get(sid, []),
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
