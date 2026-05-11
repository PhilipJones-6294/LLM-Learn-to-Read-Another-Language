VLLM_BASE_URL = "http://localhost:8000/v1"
MODEL_NAME = "/models/gemma4"   # confirm with GET /v1/models
MAX_TOKENS = 1024
TEMPERATURE = 0.2
VLLM_API_KEY = "dummy"  # Not used, but vLLM API requires an Authorization header

INPUT_PATH = "data/input/harry_potter_1.txt"
OUTPUT_PATH = "data/output/hp1_gradient.txt"
MANIFEST_PATH = "data/manifest.json"

# S-Curve parameters
SCURVE_STEEPNESS = 5
SCURVE_MIDPOINT = 0.88
MAX_BUDGET_PER_CLAUSE = 10


# Scene segmentation
MIN_SCENE_TOKENS = 300

# Clause segmentation
MAX_CLAUSE_TOKENS = 20

# Context window
LOCAL_WINDOW_BEFORE = 2
LOCAL_WINDOW_AFTER = 2

# Parity judge rollback
MAX_ROLLBACK_ATTEMPTS = 3

# Hard anchors — never substituted
EXPLICIT_ANCHORS = [
    "Harry", "Hermione", "Ron", "Dumbledore", "Voldemort",
    "Hogwarts", "Gryffindor", "Slytherin", "Hufflepuff", "Ravenclaw",
    "Muggle", "You-Know-Who", "Diagon Alley", "Privet Drive",
    "Quidditch", "Patronus", "Horcrux"
]

# ── Novel-scale architecture (two-pass frequency-first) ────────────────────────

# Ledger
LEDGER_PATH = "data/ledger.db"

# Fragment consolidation
MIN_CLUSTER_TOKENS = 3

# Clustering
CLUSTER_FUZZY_MAX_TOKENS = 8
CLUSTER_EDIT_DISTANCE_THRESHOLD = 2

# Frequency-position stage override:
# Clauses seen ≥ this many times graduate one stage early regardless of S-curve
FREQ_OVERRIDE_THRESHOLD = 20

# Contextual variation micro-prompt (IMMERSION stage + non-neutral scenes only)
ALLOW_CONTEXTUAL_VARIATION = True
VARIATION_MAX_TOKENS = 256

# N-gram frequency analysis
PHRASE_FREQ_PATH = "data/phrase_frequencies.json"
NGRAM_MIN_FREQ = 3
NGRAM_TOP_K = 200
PHRASE_CONTEXT_TOP_K = 20

# Epub structural noise patterns to strip
EPUB_STRIP_NAV_PATTERNS = [
    r"^\s*(Contents|Next Chapter|Previous Chapter|Back to top)\s*$"
]
