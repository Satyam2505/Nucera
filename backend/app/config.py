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
# Measured with llama3.2:3b on a laptop CPU: the prompt is read at ~18 tokens/s
# and the reply written at ~4 tokens/s, so a ~900-token prompt and a 300-token
# answer take 2-3 minutes. 120 s timed out on the first real question.
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))

# Context window and sampling, sent with every request. Without num_ctx Ollama
# applies its own default, and a prompt longer than that is silently cut from
# the front, which is where the grounding rules in the system prompt live. The
# prompt builders size their prompts to fit this window (see
# app/services/context_budget.py): prompt + reply must stay within NUM_CTX.
# It is one value for tutor and quiz on purpose: Ollama reloads the model when
# num_ctx changes between requests, which is slow on a CPU. Raising it costs
# memory (KV cache) and prompt-processing time, so keep it as small as works.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
# Low, because the tutor is meant to restate the material, not improvise.
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
# Longest tutor reply, in tokens (the system prompt asks for ~250 words, which is
# about 350 tokens). Also the room the prompt budget keeps free.
OLLAMA_MAX_OUTPUT_TOKENS = int(os.getenv("OLLAMA_MAX_OUTPUT_TOKENS", "600"))

# Hybrid retrieval: besides the vector ranking, rank by keyword (SQLite FTS5, when
# the database has it) and merge the two by reciprocal rank fusion. RRF_K damps how
# much the very top ranks count (60 is the usual value); LEXICAL_LIMIT is how many
# keyword hits are merged in.
RETRIEVAL_HYBRID = os.getenv("RETRIEVAL_HYBRID", "true").lower() not in ("0", "false", "no", "off")
HYBRID_RRF_K = int(os.getenv("HYBRID_RRF_K", "60"))
HYBRID_LEXICAL_LIMIT = int(os.getenv("HYBRID_LEXICAL_LIMIT", "30"))

# Below this top-match cosine similarity, retrieval is treated as "nothing
# relevant found" and the LLM is not called at all, and only chunks at or above
# it are sent to the model — see app/services/tutor_service.py. It depends on
# the embedding model AND the chunk size, so re-check it
# (tests/test_relevance_threshold.py) whenever either changes.
RETRIEVAL_RELEVANCE_THRESHOLD = float(os.getenv("RETRIEVAL_RELEVANCE_THRESHOLD", "0.35"))

# OCR for scanned PDFs (optional, local; needs `pip install -r requirements-ocr.txt`).
# A page with fewer extracted characters than OCR_MIN_TEXT_CHARS that contains an
# image is treated as a scan. OCR runs on the CPU at a few seconds per page and
# inside the upload request, so a single upload is limited to OCR_MAX_PAGES pages.
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() not in ("0", "false", "no", "off")
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "30"))
OCR_MIN_TEXT_CHARS = int(os.getenv("OCR_MIN_TEXT_CHARS", "30"))
OCR_DPI = int(os.getenv("OCR_DPI", "150"))
# Lines the engine is less sure of than this are dropped rather than added as noise.
OCR_MIN_CONFIDENCE = float(os.getenv("OCR_MIN_CONFIDENCE", "0.5"))

# Largest accepted upload. The cap protects the server (a file is read into
# memory to extract its text), not the user's disk.
UPLOAD_MAX_BYTES = int(float(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024)

# Quiz generation. Writing several questions takes a local CPU model much
# longer than a tutor answer, hence its own (longer) timeout. Measured with
# llama3.2:3b on a CPU: about 5 tokens/s, and a five-question JSON reply is
# roughly 1,100-1,400 tokens, i.e. 220-280 s on a warm model and more on a
# cold one, so 240 s timed out; 600 s leaves room. The excerpt limits keep
# the prompt within a small model's context.
#
# Quizzes are written one question per model call, in a background job. Three
# questions by default: at ~4 tokens/s each call is about two minutes.
QUIZ_QUESTION_COUNT = int(os.getenv("QUIZ_QUESTION_COUNT", "3"))
# Excerpts of the material given to the model for each question. Each one costs
# prompt-reading time (~18 tokens/s on a CPU), so few, chosen differently for each
# question, rather than all of the material every time.
QUIZ_MAX_EXCERPTS = int(os.getenv("QUIZ_MAX_EXCERPTS", "3"))
# A running quiz job that hasn't reported progress for this long is treated as
# dead (its worker crashed) and no longer blocks the topic. Longer than two model
# timeouts, the most one question can take.
QUIZ_JOB_STALE_SECONDS = float(os.getenv("QUIZ_JOB_STALE_SECONDS", "1500"))
QUIZ_CONTEXT_CHAR_BUDGET = int(os.getenv("QUIZ_CONTEXT_CHAR_BUDGET", "9000"))
QUIZ_LLM_TIMEOUT_SECONDS = float(os.getenv("QUIZ_LLM_TIMEOUT_SECONDS", "600"))
# Quiz sampling is a little warmer than the tutor's so regenerating a quiz
# doesn't reproduce it, but still low enough to keep the JSON well-formed.
QUIZ_TEMPERATURE = float(os.getenv("QUIZ_TEMPERATURE", "0.4"))
# Room reserved for the reply, per question (a measured question is ~220-280
# tokens of JSON). The excerpts get whatever is left of OLLAMA_NUM_CTX after
# this and the system prompt, up to QUIZ_CONTEXT_CHAR_BUDGET.
QUIZ_TOKENS_PER_QUESTION = int(os.getenv("QUIZ_TOKENS_PER_QUESTION", "300"))

# Auth. JWT_SECRET_KEY MUST be overridden via env in any real deployment —
# the fallback only exists so local dev works out of the box on a single
# machine with no other users.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 days
