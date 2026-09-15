"""Local, CPU-only embeddings via sentence-transformers.

No paid APIs, no cloud calls. The model is loaded once (lazily, on first
use) and reused for every request. Everything downstream — ingestion,
retrieval — only ever calls generate_embedding()/embed_texts(), so the
model can be swapped later (a bigger one, a different family) by editing
this file alone.
"""

from typing import List, Optional

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2's native output size

_model: Optional[object] = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Batch-embed several chunks at once — meaningfully faster than calling
    generate_embedding() in a loop, since it amortizes one model call
    instead of many.
    """
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return [v.tolist() for v in vectors]


def generate_embedding(text: str) -> List[float]:
    """Embed a single piece of text. Thin wrapper around embed_texts() so
    existing single-item call sites keep working unchanged.
    """
    return embed_texts([text])[0]
