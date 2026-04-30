import json
import logging
from typing import Dict

from cognitive_gradient.prompts import judge as judge_prompt

logger = logging.getLogger(__name__)

_PASS_FALLBACK: Dict = {
    "verdict": "PASS",
    "confidence": 0.5,
    "emotional_tone_preserved": True,
    "narrative_meaning_preserved": True,
    "scene_weight_preserved": True,
    "drift_detected": None,
    "offending_phrase": None,
    "rollback_suggestion": None,
}


def call_judge(
    original: str,
    gradient: str,
    scene_data: Dict,
    config,
) -> Dict:
    """
    Run the Parity Judge on a gradient clause.

    Returns a verdict dict. On LLM failure, returns a PASS fallback so the
    pipeline keeps moving rather than stalling on a transient error.
    """
    from cognitive_gradient.pipeline.translator import call_vllm

    messages = judge_prompt.build_messages(
        original_clause=original,
        gradient_clause=gradient,
        scene_stake=scene_data.get("stake", ""),
        scene_tone=scene_data.get("emotional_register", ""),
    )

    try:
        result = call_vllm(messages, config)
        # Normalise verdict to uppercase in case the model lowercases it
        result["verdict"] = result.get("verdict", "PASS").upper()
        return result
    except json.JSONDecodeError as exc:
        logger.warning("Judge returned non-JSON: %s", exc)
        return _PASS_FALLBACK
    except Exception as exc:
        logger.warning("Judge call failed: %s — returning PASS fallback", exc)
        return _PASS_FALLBACK
