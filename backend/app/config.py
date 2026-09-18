import os

from dotenv import load_dotenv

load_dotenv()

# SQLite by default — this is a personal, solo-use local app (see README),
# so it needs no server/Docker/install. Override with a real Postgres URL
# via the DATABASE_URL env var if you want that instead.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

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

# Auth. JWT_SECRET_KEY MUST be overridden via env in any real deployment —
# the fallback only exists so local dev works out of the box on a single
# machine with no other users.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 days
