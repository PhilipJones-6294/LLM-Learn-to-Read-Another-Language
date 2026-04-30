VLLM_BASE_URL = "http://localhost:8000/v1"
MODEL_NAME = "google/gemma-4-31b-it"   # confirm with GET /v1/models
MAX_TOKENS = 1024
TEMPERATURE = 0.2

INPUT_PATH = "data/input/harry_potter_1.txt"
OUTPUT_PATH = "data/output/hp1_gradient.txt"
MANIFEST_PATH = "data/manifest.json"

SCURVE_STEEPNESS = 8
SCURVE_MIDPOINT = 0.55
MAX_BUDGET_PER_CLAUSE = 10

MIN_SCENE_TOKENS = 300
MAX_CLAUSE_TOKENS = 20

LOCAL_WINDOW_BEFORE = 2
LOCAL_WINDOW_AFTER = 2

MAX_ROLLBACK_ATTEMPTS = 3

EXPLICIT_ANCHORS = [
    "Harry", "Hermione", "Ron", "Dumbledore", "Voldemort",
    "Hogwarts", "Gryffindor", "Slytherin", "Hufflepuff", "Ravenclaw",
    "Muggle", "You-Know-Who", "Diagon Alley", "Privet Drive",
    "Quidditch", "Patronus", "Horcrux"
]
