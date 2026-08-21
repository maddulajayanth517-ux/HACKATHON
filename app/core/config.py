import os

DUPLICATE_DISTANCE_METERS = float(
    os.getenv("DUPLICATE_DISTANCE_METERS", "15")
)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen3:4b"
)