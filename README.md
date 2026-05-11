# Cognitive Gradient Engine

A Python pipeline that takes a novel in English and produces a single output file that gradually migrates to French — starting at ~100% English in chapter 1 and arriving at ~100% French by the final chapter.

The transition is clause by clause, driven by a logistic S-curve. The reader is assumed to have already read the novel in their native language. The goal is **immersion**, not translation. By the end, the reader thinks in French.

---

## What It Does

```
Chapter 1:   Mr. and Mrs. Dursley, of number four, Privet Drive, were proud to say...
Chapter 8:   Harry felt le petit frisson of excitement as il monta l'escalier...
Chapter 17:  Harry regarda Dumbledore, les yeux écarquillés. «C'est impossible,» dit-il.
```

No metadata. No side-by-side columns. Just the novel, shifting beneath the reader.

---

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU VRAM | 24 GB (for 4-bit quant) | 40 GB+ |
| RAM | 32 GB | 64 GB |
| Storage | 40 GB (model weights) | 80 GB |
| GPU | RTX 4090 / A100 | DGX Spark / H100 |

The pipeline is built around **Gemma 4 31B in NVfp4 quantization** via vLLM. A single RTX 4090 (24 GB) can run it in 4-bit; the DGX Spark runs it comfortably with headroom.

---

## Software Requirements

- **Python 3.10 or newer**
- **CUDA 12.x** and matching GPU drivers
- **vLLM** — the inference server (runs separately from this pipeline)
- The Python packages listed in `requirements.txt`

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/philipjones-6294/llm-learn-to-read-another-language.git
cd llm-learn-to-read-another-language
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Download the spaCy language model

The transformer-based model is slower but significantly more accurate for clause and scene detection:

```bash
python -m spacy download en_core_web_trf
```

If you need a faster fallback (less accurate clause segmentation):

```bash
python -m spacy download en_core_web_sm
```

### 5. Install and start vLLM

vLLM is the inference server. It runs as a separate process and exposes an OpenAI-compatible API that the pipeline calls.

```bash
pip install vllm
```

Start the server (adjust `--gpu-memory-utilization` for your hardware):

```bash
python -m vllm.entrypoints.openai.api_server \
    --model google/gemma-4-31b-it \
    --quantization fp8 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 65536
```

Verify the server is running:

```bash
curl http://localhost:8000/v1/models
```

The model name in the response must match `MODEL_NAME` in `config.py`.

---

## Input File

Place your novel as a plain text or epub file in `data/input/`:

```
data/input/harry_potter_1.txt
data/input/my_novel.epub
```

**Plain text (`.txt`)** — works best when the file is a clean Gutenberg-style text. The cleaner handles OCR artifacts, hard hyphen line breaks, stray page numbers, and excess blank lines automatically.

**EPUB (`.epub`)** — the pipeline extracts body text and strips HTML, navigation elements, footnotes, and Unicode smart-quote variants before processing.

Then update `INPUT_PATH` in `config.py` to match your file.

---

## Configuration

All tunable parameters are in `cognitive_gradient/config.py`. Nothing is hardcoded elsewhere.

### Paths

| Key | Default | Description |
|-----|---------|-------------|
| `INPUT_PATH` | `data/input/harry_potter_1.txt` | Novel to process |
| `OUTPUT_PATH` | `data/output/hp1_gradient.txt` | Final gradient novel |
| `MANIFEST_PATH` | `data/manifest.json` | Cached preprocessing output |
| `LEDGER_PATH` | `data/ledger.db` | SQLite translation ledger |
| `PHRASE_FREQ_PATH` | `data/phrase_frequencies.json` | N-gram frequency map |

### vLLM / Model

| Key | Default | Description |
|-----|---------|-------------|
| `VLLM_BASE_URL` | `http://localhost:8000/v1` | vLLM server URL |
| `MODEL_NAME` | `google/gemma-4-31b-it` | Must match what vLLM reports at `/v1/models` |
| `MAX_TOKENS` | `1024` | Max tokens per translator/judge response |
| `TEMPERATURE` | `0.2` | Low = more deterministic substitution |

### S-Curve (gradient shape)

The entire English→French arc is controlled by a logistic S-curve applied to each clause's position in the novel (0.0 = first clause, 1.0 = last).

| Key | Default | Effect |
|-----|---------|--------|
| `SCURVE_STEEPNESS` | `8` | Higher = sharper transition at the midpoint |
| `SCURVE_MIDPOINT` | `0.55` | Novel position where transition is fastest |
| `MAX_BUDGET_PER_CLAUSE` | `10` | Hard cap: no clause gets more than 10 substitutions |

**Stages** determined from S-curve intensity:

| Stage | Intensity | Behaviour |
|-------|-----------|-----------|
| `COGNATE` | < 0.25 | Cognates only, no word-order change |
| `INFERABLE` | 0.25 – 0.65 | Context-inferable words, mild restructuring |
| `IMMERSION` | ≥ 0.65 | Full French meaning and syntax |

### Segmentation

| Key | Default | Description |
|-----|---------|-------------|
| `MIN_SCENE_TOKENS` | `300` | A scene must accumulate this many tokens before a boundary can split it |
| `MAX_CLAUSE_TOKENS` | `20` | Clauses longer than this are chunked at the nearest comma or conjunction |
| `MIN_CLUSTER_TOKENS` | `3` | Clause fragments shorter than this are merged into neighbours |

### Novel-scale performance

| Key | Default | Description |
|-----|---------|-------------|
| `FREQ_OVERRIDE_THRESHOLD` | `20` | Clauses appearing ≥ N times graduate one stage early (repetition primes the reader) |
| `CLUSTER_FUZZY_MAX_TOKENS` | `8` | Max clause length eligible for fuzzy-match clustering |
| `CLUSTER_EDIT_DISTANCE_THRESHOLD` | `2` | Levenshtein distance for Tier 3 cluster matching |
| `ALLOW_CONTEXTUAL_VARIATION` | `True` | In IMMERSION + non-neutral scenes, apply a micro-prompt to adjust agreement and punctuation on ledger hits |
| `VARIATION_MAX_TOKENS` | `256` | Token budget for the variation micro-prompt |

### Hard anchors

Words that are **never substituted**, regardless of stage or budget:

```python
EXPLICIT_ANCHORS = [
    "Harry", "Hermione", "Ron", "Dumbledore", "Voldemort",
    "Hogwarts", "Gryffindor", "Slytherin", ...
]
```

Proper nouns detected by spaCy NER are also treated as hard anchors automatically. Add any title-specific terms here.

---

## Running

All three invocation styles work from the project root:

```bash
# Option A — convenience launcher
python run.py

# Option B — module invocation
python -m cognitive_gradient.main

# Option C — direct file invocation
python cognitive_gradient/main.py
```

### CLI options

| Flag | Description |
|------|-------------|
| `--chapter N` | Process only chapter N. Use this to validate the gradient before running the full novel |
| `--force-preprocess` | Re-run segmentation and scene summarisation even if `manifest.json` already exists |
| `--input PATH` | Override `INPUT_PATH` from config |
| `--output PATH` | Override `OUTPUT_PATH` from config |

### Recommended first run

```bash
# 1. Validate on a single chapter first
python run.py --chapter 1

# 2. Read data/output/hp1_gradient.txt — does the gradient feel right?
#    Tune SCURVE_MIDPOINT and SCURVE_STEEPNESS in config.py if needed.

# 3. Run the full novel
python run.py --force-preprocess
```

---

## Pipeline Overview

The pipeline runs in two passes.

```
INPUT (.txt or .epub)
    │
    ▼
INGEST & CLEAN
    clean()          OCR artifacts, epub unicode/structural pre-pass
    │
    ▼
N-GRAM ANALYSIS
    ngram_analyze()  Bigram/trigram/4-gram frequency map
                     Top-20 high-value phrases stamped on each clause
    │
    ▼
PREPROCESSING  (runs once, results cached to manifest.json)
    segment()        spaCy dep-parse → clause list + scene boundaries
    consolidate()    Merge sub-3-token fragments into neighbours
    assign_positions() S-curve position/budget/stage per clause
    summarize()      LLM scene summaries (stake, tone, soft anchors)
    │
    ▼
PASS 1 — FREQUENCY-FIRST LEDGER BUILD
    cluster_clauses()   Group near-duplicate clauses (exact → normalised → fuzzy)
    Rank by frequency   Most common clauses translated first
    translate_canonical() LLM call once per cluster using longest member
    ledger.write()      SQLite: normalised_text → gradient, stage, cost
    │
    ▼
PASS 2 — FULL NOVEL TRANSLATION (novel order)
    For each clause:
        ledger.lookup()          Hit → return cached gradient
        apply_variation()        IMMERSION + non-neutral scene → micro-prompt adjust
        process_clause()         Miss → Translator LLM + Parity Judge rollback loop
    │
    ▼
STITCH
    Reassemble paragraphs, chapter headings, dialogue punctuation → output .txt
```

### LLM call reduction at novel scale

| Scenario | Calls (before) | Calls (after) |
|----------|---------------|---------------|
| Chapter 1 (~365 clauses) | ~180 | ~180 — ledger empty |
| Full novel (~5,000 clauses) | ~2,500 | ~400–600 |
| Re-run after config change | ~2,500 | ~0–50 — ledger hits |

---

## Generated Files

After a run, `data/` will contain:

| File | Description |
|------|-------------|
| `data/manifest.json` | Preprocessed clause/scene data. Delete and re-run with `--force-preprocess` if the input changes |
| `data/ledger.db` | SQLite translation ledger. Safe to keep across runs for resume support. Delete to start fresh |
| `data/phrase_frequencies.json` | N-gram frequency map for the input novel |
| `data/flagged_clauses.log` | Clauses that exhausted all rollback attempts. Review manually if the output has drift |
| `data/output/<name>.txt` | The final gradient novel |

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'cognitive_gradient'`**  
Run from the project root using `python run.py` or `python -m cognitive_gradient.main`, not from inside the `cognitive_gradient/` directory.

**`ConnectionRefusedError` / `requests` timeout**  
The vLLM server is not running or is not reachable at `VLLM_BASE_URL`. Start it first and confirm with `curl http://localhost:8000/v1/models`.

**Model name mismatch**  
The name returned by `/v1/models` must exactly match `MODEL_NAME` in `config.py`. Update config if vLLM uses a shortened alias.

**spaCy `OSError: [E050]` — model not found**  
Run `python -m spacy download en_core_web_trf`. If you only have `en_core_web_sm` installed the pipeline will fall back to it automatically with a warning.

**Gradient feels too abrupt / too slow**  
Adjust `SCURVE_STEEPNESS` (sharpness) and `SCURVE_MIDPOINT` (where the fastest transition happens). Test on chapter 1 with `--chapter 1` before re-running the full novel.

**Output has character-name drift in late chapters**  
Add the drifting name to `EXPLICIT_ANCHORS` in `config.py` and re-run with `--force-preprocess`.

---

## Project Structure

```
cognitive_gradient/
├── config.py                   All tunable parameters
├── main.py                     Pipeline orchestration
├── preprocessing/
│   ├── cleaner.py              OCR + epub pre-cleaning
│   ├── loader.py               .txt / .epub ingestion
│   ├── segmenter.py            spaCy clause + scene segmentation
│   ├── ngram_analyzer.py       Bigram/trigram/4-gram frequency map
│   ├── fragment_consolidator.py  Merge sub-3-token clause orphans
│   ├── summarizer.py           LLM scene summaries (runs once)
│   └── manifest.py             Build + cache manifest.json
├── pipeline/
│   ├── budget.py               S-curve math + position assignment
│   ├── clusterer.py            Clause clustering (exact/norm/fuzzy)
│   ├── ledger.py               SQLite translation ledger
│   ├── translator.py           Translator LLM + rollback loop
│   ├── judge.py                Parity Judge LLM
│   ├── variation.py            IMMERSION micro-prompt for agreement
│   └── stitcher.py             Reassemble clauses → final file
└── prompts/
    ├── scene_summarizer.py     Scene summariser prompt template
    ├── translator.py           Translator prompt template
    └── judge.py                Parity Judge prompt template

data/
├── input/                      Place your .txt or .epub here
└── output/                     Gradient novel is written here

run.py                          Top-level launcher
requirements.txt
```
