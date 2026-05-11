import json
import logging
from typing import Dict, List

from cognitive_gradient.prompts import scene_summarizer as summarizer_prompt

logger = logging.getLogger(__name__)


def _call_vllm(messages: list, config) -> dict:
    import requests

    response = requests.post(
        f"{config.VLLM_BASE_URL}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {getattr(config, 'VLLM_API_KEY', 'dummy')}",
        },
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
    content = content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(content)


def _fallback_summary(scene_id: str) -> Dict:
    return {
        "scene_id": scene_id,
        "stake": "Events unfold in this scene.",
        "emotional_register": "neutral",
        "soft_anchors": [],
    }


def summarize_scenes(scenes: List[Dict], config) -> List[Dict]:
    """
    Call the LLM once per scene to produce scene summaries.
    Returns a list of summary dicts in the same order as scenes.
    """
    summaries: List[Dict] = []

    for scene in scenes:
        scene_id = scene["scene_id"]
        scene_text = scene.get("text", "")

        # Truncate very long scenes to fit context — summaries only need the gist
        words = scene_text.split()
        if len(words) > 800:
            scene_text = " ".join(words[:800]) + " [...]"

        messages = summarizer_prompt.build_messages(scene_id=scene_id, scene_text=scene_text)

        try:
            result = _call_vllm(messages, config)
            # Ensure required keys are present
            summary = {
                "scene_id": result.get("scene_id", scene_id),
                "stake": result.get("stake", ""),
                "emotional_register": result.get("emotional_register", "neutral"),
                "soft_anchors": result.get("soft_anchors", [])[:8],
            }
        except Exception as exc:
            logger.warning("Scene summarizer failed for %s: %s — using fallback", scene_id, exc)
            summary = _fallback_summary(scene_id)

        summaries.append(summary)
        logger.debug("Summarized %s: %s", scene_id, summary["stake"])

    return summaries
