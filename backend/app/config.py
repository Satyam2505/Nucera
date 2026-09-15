import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/edupilot"
)

# Local LLM (Ollama) — no cloud calls, no paid APIs. Model name is
# configurable so a different local model can be swapped in without code
# changes anywhere else.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

# Below this top-match cosine similarity, retrieval is treated as "nothing
# relevant found" and the LLM is not called at all — see
# app/services/tutor_service.py. Tuned empirically against real retrieval
# results (see backend/tests and the milestone verification notes).
RETRIEVAL_RELEVANCE_THRESHOLD = float(os.getenv("RETRIEVAL_RELEVANCE_THRESHOLD", "0.35"))
