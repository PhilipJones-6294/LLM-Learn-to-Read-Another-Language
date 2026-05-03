import re
from typing import Dict, List

from cognitive_gradient.pipeline.ledger import _edit_distance


def _normalize(text: str) -> str:
    """Lowercase, strip surrounding quotes, remove punctuation, collapse spaces."""
    text = text.lower().strip().strip("\"'")
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def cluster_clauses(clauses: List[Dict], config) -> List[Dict]:
    """
    Group clauses into clusters by similarity.

    Tier 1 — Exact match (hash)
    Tier 2 — Normalized match (lowercase + strip punctuation/quotes)
    Tier 3 — Fuzzy Levenshtein ≤ 2 on normalized form, for 4–CLUSTER_FUZZY_MAX_TOKENS
              token clauses that are not IMMERSION-stage singletons.

    Each cluster carries the canonical form (longest member, tie-break by most
    hard anchors), total_occurrences, and a member list with clause_id, text,
    position, stage, and hard_anchors.

    Positions must be pre-assigned on clause dicts before calling this function.
    """
    max_fuzzy = getattr(config, "CLUSTER_FUZZY_MAX_TOKENS", 8)
    edit_thresh = getattr(config, "CLUSTER_EDIT_DISTANCE_THRESHOLD", 2)

    exact_to_cid: Dict[str, str] = {}
    norm_to_cid: Dict[str, str] = {}
    clusters: Dict[str, Dict] = {}

    for clause in clauses:
        text = clause["text"]
        norm = _normalize(text)
        tc = len(text.split())
        pos = clause.get("position", 0.0)
        stage = clause.get("stage", "COGNATE")
        hard_anchors = clause.get("hard_anchors", [])

        member_entry = {
            "clause_id": clause["clause_id"],
            "text": text,
            "position": pos,
            "stage": stage,
            "hard_anchors": hard_anchors,
            "tier": 1,
        }

        # Tier 1
        if text in exact_to_cid:
            cid = exact_to_cid[text]
            clusters[cid]["members"].append(member_entry)
            clusters[cid]["total_occurrences"] += 1
            _update_canonical(clusters[cid])
            continue

        # Tier 2
        if norm in norm_to_cid:
            cid = norm_to_cid[norm]
            member_entry["tier"] = 2
            exact_to_cid[text] = cid
            clusters[cid]["members"].append(member_entry)
            clusters[cid]["total_occurrences"] += 1
            _update_canonical(clusters[cid])
            continue

        # New singleton cluster
        cid = f"cluster_{len(clusters):06d}"
        exact_to_cid[text] = cid
        norm_to_cid[norm] = cid
        clusters[cid] = {
            "cluster_id": cid,
            "canonical": text,
            "canonical_tokens": tc,
            "canonical_hard_anchors": hard_anchors,
            "total_occurrences": 1,
            "members": [member_entry],
            "gradient": None,
            "ledger_status": "pending",
        }

    # Tier 3: Fuzzy match — singleton short clauses only
    _apply_fuzzy_tier(clusters, max_fuzzy, edit_thresh)

    return list(clusters.values())


def _update_canonical(cluster: Dict) -> None:
    """Replace canonical with longest member; tie-break on most hard anchors."""
    best = max(
        cluster["members"],
        key=lambda m: (len(m["text"].split()), len(m.get("hard_anchors", []))),
    )
    cluster["canonical"] = best["text"]
    cluster["canonical_tokens"] = len(best["text"].split())
    cluster["canonical_hard_anchors"] = best.get("hard_anchors", [])


def _apply_fuzzy_tier(
    clusters: Dict[str, Dict], max_fuzzy: int, edit_thresh: int
) -> None:
    """
    In-place: merge singleton clusters within edit distance of each other.
    Only eligible for short (4–max_fuzzy token) non-IMMERSION singletons.
    """
    cids = list(clusters.keys())
    merged: set = set()

    for i in range(len(cids)):
        ci_id = cids[i]
        if ci_id in merged or ci_id not in clusters:
            continue
        ci = clusters[ci_id]
        if ci["total_occurrences"] > 1:
            continue
        if not (4 <= ci["canonical_tokens"] <= max_fuzzy):
            continue
        if any(m.get("stage") == "IMMERSION" for m in ci["members"]):
            continue

        norm_i = _normalize(ci["canonical"])

        for j in range(i + 1, len(cids)):
            cj_id = cids[j]
            if cj_id in merged or cj_id not in clusters:
                continue
            cj = clusters[cj_id]
            if cj["total_occurrences"] > 1:
                continue
            if not (4 <= cj["canonical_tokens"] <= max_fuzzy):
                continue
            if any(m.get("stage") == "IMMERSION" for m in cj["members"]):
                continue

            norm_j = _normalize(cj["canonical"])
            if _edit_distance(norm_i, norm_j) <= edit_thresh:
                # Merge j into i
                ci["members"].extend(cj["members"])
                ci["total_occurrences"] += cj["total_occurrences"]
                _update_canonical(ci)
                merged.add(cj_id)
                break  # one merge per singleton is enough

    for cid in merged:
        del clusters[cid]
