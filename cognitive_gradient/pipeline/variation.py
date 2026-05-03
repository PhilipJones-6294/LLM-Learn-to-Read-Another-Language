import logging
from typing import Dict

logger = logging.getLogger(__name__)

_SYSTEM = """You are a micro-adjustment engine for French text.

You will receive a French clause and its local context.
Your ONLY job is to adjust morphology and punctuation to fit the local context.

Rules:
- Do NOT change word choice or substitution decisions
- Do NOT change meaning
- Adjust only: number agreement (dit/dirent), article selection (le/la/l'), dialogue punctuation
- If no adjustment is needed, return the gradient unchanged

Return ONLY valid JSON. No explanation. No preamble. No markdown fences.

{
  "adjusted": "<the adjusted French clause>",
  "changed": true
}"""

_USER_TEMPLATE = (
    'GRADIENT: "{gradient}"\n'
    'LOCAL_BEFORE: "{local_before}"\n'
    'LOCAL_AFTER: "{local_after}"\n'
    'SCENE_STAKE: "{scene_stake}"\n'
    'SCENE_TONE: "{scene_tone}"'
)


def apply_variation(
    gradient: str,
    clause_data: Dict,
    scene_data: Dict,
    config,
) -> str:
    """
    Micro-prompt contextual variation for IMMERSION-stage ledger hits.

    Adjusts morphology/punctuation to match local context without re-translating.
    Falls back to the unmodified gradient on any LLM failure.
    """
    from cognitive_gradient.pipeline.translator import call_vllm

    local_before = " | ".join(clause_data.get("local_before", []))
    local_after = " | ".join(clause_data.get("local_after", []))

    # Build a lightweight config override for reduced token budget
    class _VariationConfig:
        VLLM_BASE_URL = config.VLLM_BASE_URL
        MODEL_NAME = config.MODEL_NAME
        MAX_TOKENS = getattr(config, "VARIATION_MAX_TOKENS", 256)
        TEMPERATURE = config.TEMPERATURE

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": _USER_TEMPLATE.format(
                gradient=gradient,
                local_before=local_before,
                local_after=local_after,
                scene_stake=scene_data.get("stake", ""),
                scene_tone=scene_data.get("emotional_register", ""),
            ),
        },
    ]

    try:
        result = call_vllm(messages, _VariationConfig())
        return result.get("adjusted", gradient)
    except Exception as exc:
        logger.debug("Variation micro-prompt failed: %s — returning ledger gradient", exc)
        return gradient
