import json
import logging
import os
from typing import Dict, List, Optional

import requests

from cognitive_gradient.prompts import translator as translator_prompt

logger = logging.getLogger(__name__)

_FLAGGED_LOG = "data/flagged_clauses.log"


def call_vllm(messages: list, config) -> dict:
    """POST to the vLLM OpenAI-compatible endpoint and return parsed JSON."""
    response = requests.post(
        f"{config.VLLM_BASE_URL}/chat/completions",
        json={
            "model": config.MODEL_NAME,
            "messages": messages,
            "max_tokens": config.MAX_TOKENS,
            "temperature": config.TEMPERATURE,
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    # Strip accidental markdown fences before parsing
    content = content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(content)


def call_translator(
    clause_data: Dict,
    scene_data: Dict,
    excluded_phrases: List[str],
    config,
) -> Dict:
    """
    Call the Translator LLM for a single clause.

    excluded_phrases: French phrases flagged by the Judge on prior attempts;
    the prompt instructs the model not to reuse them.
    """
    messages = translator_prompt.build_messages(
        clause=clause_data["text"],
        stage=clause_data["stage"],
        budget=clause_data["budget"],
        hard_anchors=clause_data.get("hard_anchors", []),
        soft_anchors=scene_data.get("soft_anchors", []),
        local_before=clause_data.get("local_before", []),
        local_after=clause_data.get("local_after", []),
        scene_stake=scene_data.get("stake", ""),
        scene_tone=scene_data.get("emotional_register", ""),
        excluded_phrases=excluded_phrases,
    )
    return call_vllm(messages, config)


def _log_flagged_clause(clause_id: str, gradient_result: Dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(_FLAGGED_LOG)), exist_ok=True)
    with open(_FLAGGED_LOG, "a", encoding="utf-8") as f:
        f.write(f"FLAGGED: {clause_id}\n")
        f.write(f"  Gradient: {gradient_result.get('gradient', '')}\n")
        f.write("---\n")


def process_clause(clause_data: Dict, scene_data: Dict, config) -> str:
    """
    Translate a single clause through the rollback loop.

    1. Call translator
    2. Call parity judge
    3. On FAIL: add offending phrase to exclusion list and retry
    4. After MAX_ROLLBACK_ATTEMPTS: flag and return best attempt
    """
    from cognitive_gradient.pipeline.judge import call_judge

    excluded_phrases: List[str] = []
    last_gradient_result: Optional[Dict] = None
    original_text = clause_data["text"]

    # Budget 0 at COGNATE stage — return original immediately to save LLM calls
    if clause_data.get("budget", 0) == 0 and clause_data.get("stage") == "COGNATE":
        return original_text

    for attempt in range(config.MAX_ROLLBACK_ATTEMPTS):
        try:
            gradient_result = call_translator(
                clause_data, scene_data, excluded_phrases, config
            )
            last_gradient_result = gradient_result
        except Exception as exc:
            logger.warning(
                "Translator failed for %s (attempt %d): %s",
                clause_data["clause_id"],
                attempt + 1,
                exc,
            )
            # Return original on unrecoverable translator error
            return original_text

        gradient_text = gradient_result.get("gradient", original_text)

        try:
            verdict = call_judge(original_text, gradient_text, scene_data, config)
        except Exception as exc:
            logger.warning("Judge failed for %s: %s — accepting gradient", clause_data["clause_id"], exc)
            return gradient_text

        if verdict["verdict"] == "PASS":
            return gradient_text

        # FAIL — collect the rollback suggestion and retry
        rollback = verdict.get("rollback_suggestion")
        if rollback and rollback not in excluded_phrases:
            excluded_phrases.append(rollback)
            logger.debug(
                "Clause %s attempt %d FAIL — excluding %r",
                clause_data["clause_id"],
                attempt + 1,
                rollback,
            )

    # Exhausted retries
    _log_flagged_clause(clause_data["clause_id"], last_gradient_result or {})
    logger.warning("Max rollback attempts reached for %s", clause_data["clause_id"])
    # Return the last gradient rather than the original — it's usually acceptable
    return last_gradient_result.get("gradient", original_text) if last_gradient_result else original_text
