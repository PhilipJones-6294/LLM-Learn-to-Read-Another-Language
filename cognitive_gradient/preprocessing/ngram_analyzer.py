import json
import os
import re
from collections import Counter
from typing import Dict, List

STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "it", "he",
    "she", "they", "we", "you", "i", "me", "him", "her", "them", "us",
    "his", "their", "our", "your", "my", "its", "this", "that", "these",
    "those", "not", "no", "so", "if", "then", "than", "when", "where",
    "who", "what", "which", "how", "all", "more", "just", "up", "out",
    "about", "there", "one", "had", "her", "been", "into", "over",
})


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _is_stopword_only(gram: tuple) -> bool:
    return all(t in STOPWORDS for t in gram)


def analyse(text: str, config) -> Dict:
    """
    Extract bigram, trigram, and 4-gram frequencies from the full novel text.
    Returns a dict with a 'phrases' list sorted by frequency descending.
    """
    min_freq: int = getattr(config, "NGRAM_MIN_FREQ", 3)
    top_k: int = getattr(config, "NGRAM_TOP_K", 200)

    tokens = _tokenize(text)
    counter: Counter = Counter()

    for n in (2, 3, 4):
        for i in range(len(tokens) - n + 1):
            counter[tuple(tokens[i : i + n])] += 1

    phrases: List[Dict] = []
    for gram, freq in counter.most_common():
        if freq < min_freq:
            break
        sw_only = _is_stopword_only(gram)
        phrases.append(
            {
                "phrase": " ".join(gram),
                "ngram_size": len(gram),
                "frequency": freq,
                "rank": 0,
                "is_stopword_only": sw_only,
                "priority_substitute": not sw_only,
            }
        )

    phrases = phrases[:top_k]
    for i, p in enumerate(phrases):
        p["rank"] = i + 1

    return {"phrases": phrases}


def save(phrase_map: Dict, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(phrase_map, f, ensure_ascii=False, indent=2)


def priority_phrases(phrase_map: Dict, top_k: int = 20) -> List[str]:
    """Return the top-k priority (non-stopword) phrase strings."""
    return [
        p["phrase"]
        for p in phrase_map.get("phrases", [])
        if p.get("priority_substitute", False)
    ][:top_k]
