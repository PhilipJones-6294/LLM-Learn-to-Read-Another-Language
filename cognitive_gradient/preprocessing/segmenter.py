import re
from typing import Dict, List, Tuple

TIME_MARKERS = [
    "the next morning", "three days later", "later that", "that night",
    "the following", "the next day", "hours later", "minutes later",
    "that afternoon", "that morning", "that evening", "days later",
    "weeks later", "months later", "a moment later", "some time later",
    "a few days later", "a few hours later", "a few minutes later",
    "the next evening", "early the next", "that same", "the following day",
    "the following morning", "the following evening", "the following night",
]

POV_MARKERS = [
    "meanwhile,", "elsewhere,", "at that moment,", "back at",
    "at the same time,", "far away,", "far from there",
]

CHAPTER_PATTERN = re.compile(
    r"^(chapter\s+\w+|chapter\s+\d+|\d+\.\s+\w+|[IVXLCDM]+\.\s+\w+)",
    re.IGNORECASE,
)

CLAUSE_DEPS = {"advcl", "relcl", "ccomp", "xcomp"}

NER_ANCHOR_LABELS = {"PERSON", "ORG", "GPE", "LOC", "FAC", "WORK_OF_ART", "EVENT"}


def _load_spacy():
    try:
        import spacy
        return spacy.load("en_core_web_trf")
    except OSError:
        import spacy
        try:
            return spacy.load("en_core_web_sm")
        except OSError:
            raise OSError(
                "No spaCy model found. Run: python -m spacy download en_core_web_trf"
            )


def detect_chapters(text: str) -> List[Tuple[str, str]]:
    """Split text into (heading, body) pairs. Returns at least one entry."""
    lines = text.split("\n")
    chapters = []
    current_heading = ""
    current_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and CHAPTER_PATTERN.match(stripped):
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    chapters.append((current_heading, body))
            current_heading = stripped
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            chapters.append((current_heading, body))

    return chapters if chapters else [("", text)]


def chunk_at_boundary(text: str, max_tokens: int) -> List[str]:
    """Chunk text at commas or conjunctions when it exceeds max_tokens."""
    words = text.split()
    if len(words) <= max_tokens:
        return [text]

    CONJ = {"and", "but", "or", "yet", "so", "nor", "although", "because", "while", "when", "if"}
    chunks: List[str] = []
    remaining = words[:]

    while len(remaining) > max_tokens:
        split_at = -1
        for i in range(min(max_tokens, len(remaining)) - 1, -1, -1):
            w = remaining[i]
            if w.endswith(",") or w.lower() in CONJ:
                split_at = i
                break
        if split_at == -1:
            split_at = max_tokens - 1
        chunk = " ".join(remaining[: split_at + 1]).strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at + 1 :]

    tail = " ".join(remaining).strip()
    if tail:
        chunks.append(tail)
    return [c for c in chunks if c.strip()]


def split_sentence_into_clauses(sent, max_clause_tokens: int) -> List[str]:
    """
    Split a spaCy sentence span into clause strings using the dependency parse.
    Splits at the leftmost token of each subordinate clause subtree.
    """
    if not list(sent):
        return []

    doc = sent.doc
    sent_start = sent.start
    sent_end = sent.end

    split_points: set = set()
    for token in sent:
        if token.dep_ in CLAUSE_DEPS:
            subtree_start = min(t.i for t in token.subtree)
            if subtree_start > sent_start:
                split_points.add(subtree_start)

    boundaries = sorted(split_points)
    spans: List[str] = []
    prev = sent_start
    for bp in boundaries:
        if bp > prev:
            text = doc[prev:bp].text.strip()
            if text:
                spans.append(text)
        prev = bp
    tail = doc[prev:sent_end].text.strip()
    if tail:
        spans.append(tail)

    result: List[str] = []
    for span_text in spans:
        if len(span_text.split()) > max_clause_tokens:
            result.extend(chunk_at_boundary(span_text, max_clause_tokens))
        else:
            result.append(span_text)
    return [c for c in result if c.strip()]


def _is_scene_boundary(
    prev_doc,
    curr_doc,
    curr_text: str,
    accumulated_tokens: int,
    min_scene_tokens: int,
) -> bool:
    """Return True if there is a scene shift at the current paragraph."""
    if accumulated_tokens < min_scene_tokens:
        return False

    curr_lower = curr_text.lower().strip()

    for marker in TIME_MARKERS:
        if curr_lower.startswith(marker):
            return True

    for marker in POV_MARKERS:
        if curr_lower.startswith(marker):
            return True

    if prev_doc is not None and curr_doc is not None:
        prev_locs = {e.text.lower() for e in prev_doc.ents if e.label_ in ("GPE", "LOC", "FAC")}
        curr_locs = {e.text.lower() for e in curr_doc.ents if e.label_ in ("GPE", "LOC", "FAC")}
        if prev_locs and curr_locs and not prev_locs & curr_locs:
            return True

    if prev_doc is not None:
        prev_text = prev_doc.text.strip()
        if prev_text.endswith('."') or prev_text.endswith('?"') or prev_text.endswith('!"'):
            return True

    return False


def segment(text: str, config) -> Tuple[List[Dict], List[Dict]]:
    """
    Segment novel text into clauses and scenes.

    Returns:
        all_clauses: flat list of clause dicts (position/budget/local fields filled by manifest builder)
        all_scenes:  list of scene dicts, each containing its clause dicts
    """
    nlp = _load_spacy()
    chapters = detect_chapters(text)
    all_scenes: List[Dict] = []
    all_clauses_flat: List[Dict] = []
    global_clause_idx = 0

    for ch_idx, (chapter_heading, chapter_text) in enumerate(chapters):
        chapter_num = ch_idx + 1
        raw_paras = re.split(r"\n\s*\n", chapter_text)
        paragraphs = [p.strip() for p in raw_paras if p.strip()]
        if not paragraphs:
            continue

        # Batch-parse all paragraphs to avoid redundant NLP calls
        para_docs = list(nlp.pipe(paragraphs, batch_size=16))

        # Group paragraph indices into scenes
        scene_groups: List[List[int]] = [[0]]
        accumulated_tokens = len(paragraphs[0].split())

        for i in range(1, len(paragraphs)):
            if _is_scene_boundary(
                para_docs[i - 1],
                para_docs[i],
                paragraphs[i],
                accumulated_tokens,
                config.MIN_SCENE_TOKENS,
            ):
                scene_groups.append([i])
                accumulated_tokens = len(paragraphs[i].split())
            else:
                scene_groups[-1].append(i)
                accumulated_tokens += len(paragraphs[i].split())

        for sc_idx, para_indices in enumerate(scene_groups):
            scene_id = f"ch{chapter_num:02d}_sc{sc_idx:03d}"
            scene_clauses: List[Dict] = []
            scene_text_parts: List[str] = []

            for para_i in para_indices:
                para = paragraphs[para_i]
                para_doc = para_docs[para_i]
                scene_text_parts.append(para)

                # Extract entities from the whole paragraph once
                para_entities = [
                    e.text for e in para_doc.ents if e.label_ in NER_ANCHOR_LABELS
                ]

                para_clause_texts: List[str] = []
                for sent in para_doc.sents:
                    para_clause_texts.extend(
                        split_sentence_into_clauses(sent, config.MAX_CLAUSE_TOKENS)
                    )

                for c_idx, clause_text in enumerate(para_clause_texts):
                    proper_nouns = [e for e in para_entities if e in clause_text]
                    explicit_in_clause = [
                        a for a in config.EXPLICIT_ANCHORS if a in clause_text
                    ]
                    hard_anchors = list(set(proper_nouns + explicit_in_clause))

                    clause_data: Dict = {
                        "clause_id": f"{scene_id}_cl{global_clause_idx:06d}",
                        "scene_id": scene_id,
                        "text": clause_text,
                        "position": None,
                        "budget": None,
                        "stage": None,
                        "hard_anchors": hard_anchors,
                        "paragraph_break_before": (c_idx == 0),
                        "local_before": [],
                        "local_after": [],
                    }
                    scene_clauses.append(clause_data)
                    global_clause_idx += 1

            scene: Dict = {
                "scene_id": scene_id,
                "chapter": chapter_num,
                "chapter_heading": chapter_heading,
                "stake": None,
                "emotional_register": None,
                "soft_anchors": [],
                "text": "\n\n".join(scene_text_parts),
                "clauses": scene_clauses,
            }
            all_scenes.append(scene)
            all_clauses_flat.extend(scene_clauses)

    return all_clauses_flat, all_scenes
