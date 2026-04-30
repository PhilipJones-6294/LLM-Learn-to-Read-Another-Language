import math


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
    if intensity < 0.65:
        return "INFERABLE"
    return "IMMERSION"
