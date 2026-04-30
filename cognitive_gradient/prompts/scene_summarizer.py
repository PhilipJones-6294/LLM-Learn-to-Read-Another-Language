SYSTEM = """You are a literary analyst. You will receive a passage from a novel.
Your job is to produce a compact scene summary for use by a translation engine.

Return ONLY valid JSON. No explanation. No preamble. No markdown fences.

{
  "scene_id": "<provided scene id>",
  "stake": "<one sentence: what is at stake or happening in this scene>",
  "emotional_register": "<2-4 words: dominant tone, e.g. wonder, dread, dark humor>",
  "soft_anchors": ["<word or phrase that carries plot or emotional weight>"]
}

soft_anchors: terms that are load-bearing for the story — things a translation
engine should be conservative about substituting even if budget allows.
Maximum 8 soft anchors per scene."""

USER_TEMPLATE = """SCENE_ID: {scene_id}
PASSAGE:
{scene_text}"""


def build_messages(scene_id: str, scene_text: str) -> list:
    return [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(scene_id=scene_id, scene_text=scene_text),
        },
    ]
