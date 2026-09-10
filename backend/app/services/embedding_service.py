import random

EMBEDDING_DIM = 8


def generate_embedding(text: str) -> list[float]:
    """STUB — replace with real implementation later (Sentence Transformers).

    Deterministic per input text (seeded by its hash) so re-ingesting the
    same chunk doesn't produce noisy diffs, but this carries no real
    semantic meaning — do not use for similarity search yet.
    """
    rng = random.Random(hash(text) % (2**32))
    return [round(rng.uniform(-1, 1), 4) for _ in range(EMBEDDING_DIM)]
