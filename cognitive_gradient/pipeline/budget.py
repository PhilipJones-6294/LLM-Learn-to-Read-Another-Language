import math
import statistics
from typing import Dict, List


def scurve(position: float, steepness: float, midpoint: float) -> float:
    """Return 0.0 → 1.0 substitution intensity for a given novel position."""
    return 1 / (1 + math.exp(-steepness * (position - midpoint)))


def calculate_budget(position: float, clause_token_count: int, config) -> int:
    """Return integer substitution budget for this clause."""
    intensity = scurve(position, config.SCURVE_STEEPNESS, config.SCURVE_MIDPOINT)
    raw_budget = intensity * clause_token_count * 0.8
    return min(int(raw_budget), config.MAX_BUDGET_PER_CLAUSE)


def determine_stage(position: float, config) -> str:
    """Map novel position to stage label."""
    intensity = scurve(position, config.SCURVE_STEEPNESS, config.SCURVE_MIDPOINT)
    if intensity < 0.25:
        return "COGNATE"
    if intensity < 0.60:
        return "INFERABLE"
    return "IMMERSION"


def assign_positions(clauses: List[Dict], config) -> None:
    """
    Assign position, budget, and stage to every clause in place.

    Called after consolidation so the total_clauses count is final.
    Required before clustering — clusterer reads clause['position'] and clause['stage'].
    """
    total = len(clauses)
    for idx, clause in enumerate(clauses):
        pos = idx / max(total - 1, 1)
        tc = len(clause["text"].split())
        clause["position"] = round(pos, 6)
        clause["budget"] = calculate_budget(pos, tc, config)
        clause["stage"] = determine_stage(pos, config)


def stage_for_cluster(cluster: Dict, config) -> str:
    """
    Determine the translation stage for a cluster's canonical form.

    Uses the median position of all member clauses. Applies a frequency override:
    clusters seen ≥ FREQ_OVERRIDE_THRESHOLD times graduate one stage early
    because repetition primes the reader regardless of novel position.
    """
    positions = [m["position"] for m in cluster["members"] if m.get("position") is not None]
    if not positions:
        return "COGNATE"

    median_pos = statistics.median(positions)
    base_stage = determine_stage(median_pos, config)

    if cluster["total_occurrences"] >= getattr(config, "FREQ_OVERRIDE_THRESHOLD", 20):
        if base_stage == "COGNATE":
            return "INFERABLE"
        # INFERABLE and IMMERSION do not double-jump

    return base_stage


def median_position(cluster: Dict) -> float:
    """Return median position across a cluster's members."""
    positions = [m["position"] for m in cluster["members"] if m.get("position") is not None]
    return statistics.median(positions) if positions else 0.0
