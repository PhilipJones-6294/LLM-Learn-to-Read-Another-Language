from typing import Dict, List


_PURE_PUNCT = frozenset('"\'""''.,!?;:—–-…')


def _is_pure_punctuation(text: str) -> bool:
    return bool(text.strip()) and all(c in _PURE_PUNCT or c.isspace() for c in text.strip())


def _token_count(text: str) -> int:
    return len(text.split())


def _merge(a: Dict, b: Dict, keep: str) -> Dict:
    """
    Merge two clause dicts. keep='a' means b (fragment) absorbs into a.
    keep='b' means a (fragment) absorbs into b.
    The merged clause takes paragraph_break_before=True if either had it.
    Hard anchors are unioned.
    """
    merged_text = (a["text"] + " " + b["text"]).strip()
    merged_anchors = list(set(a.get("hard_anchors", []) + b.get("hard_anchors", [])))
    para_break = a.get("paragraph_break_before", False) or b.get("paragraph_break_before", False)
    base = a if keep == "a" else b
    return {
        **base,
        "text": merged_text,
        "hard_anchors": merged_anchors,
        "paragraph_break_before": para_break,
        # Reset computed fields — manifest builder will recalculate
        "position": None,
        "budget": None,
        "stage": None,
        "local_before": [],
        "local_after": [],
    }


def consolidate_fragments(clauses: List[Dict], min_tokens: int = 3) -> List[Dict]:
    """
    Merge sub-min_tokens clauses into adjacent clauses.

    Rules applied in priority order:
      1. Pure punctuation  → merge backward unconditionally
      2. Sub-min_tokens, same paragraph, preceding ends with comma → backward
      3. Sub-min_tokens, same paragraph, preceding does NOT end with comma → forward
      4. Sub-min_tokens at paragraph boundary → forward only
    """
    if not clauses:
        return []

    # Iterate until stable (a single pass may expose new fragments after merging)
    changed = True
    result = list(clauses)

    while changed:
        changed = False
        new: List[Dict] = []
        i = 0
        skip_next = False

        while i < len(result):
            if skip_next:
                skip_next = False
                i += 1
                continue

            clause = result[i]
            tc = _token_count(clause["text"])
            is_punct = _is_pure_punctuation(clause["text"])

            if not is_punct and tc >= min_tokens:
                new.append(clause)
                i += 1
                continue

            # ── Fragment handling ──────────────────────────────────────────
            at_para_boundary = clause.get("paragraph_break_before", False)

            # Rule 1: pure punctuation → always backward
            if is_punct and new:
                new[-1] = _merge(new[-1], clause, keep="a")
                changed = True
                i += 1
                continue

            # Rules 2–3: sub-min fragment, NOT at paragraph boundary
            if not at_para_boundary and new:
                prev_ends_comma = new[-1]["text"].rstrip().endswith(",")
                if prev_ends_comma:
                    # Rule 2: backward
                    new[-1] = _merge(new[-1], clause, keep="a")
                    changed = True
                    i += 1
                    continue
                else:
                    # Rule 3: forward
                    if i + 1 < len(result):
                        new.append(_merge(clause, result[i + 1], keep="b"))
                        skip_next = True
                        changed = True
                        i += 1
                        continue

            # Rule 4: at paragraph boundary → forward only
            if at_para_boundary and i + 1 < len(result):
                new.append(_merge(clause, result[i + 1], keep="b"))
                skip_next = True
                changed = True
                i += 1
                continue

            # Cannot merge (first clause with no predecessor, or tail with no successor)
            new.append(clause)
            i += 1

        result = new

    return result
