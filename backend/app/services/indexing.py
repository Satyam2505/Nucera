"""Chunking text the way it will be embedded.

One place decides how text becomes chunks, used by both ingestion (a new
upload) and re-indexing (rebuilding old chunks), so the two can't drift apart.
"""

from typing import List, Optional, Tuple

from app.services.chunking import ChunkPiece, chunk_pages
from app.services.embedding_service import count_tokens, max_input_tokens


def chunk_for_embedding(pages: List[Tuple[Optional[int], str]]) -> List[ChunkPiece]:
    """Chunk `pages` ((page number or None, text) pairs) so that every chunk fits
    the embedding model's input limit. Page attribution is kept: a chunk never
    spans two pages.
    """
    if not any(text.strip() for _, text in pages):
        return []  # nothing to chunk; don't load the model just to find that out
    return chunk_pages(pages, token_counter=count_tokens, max_tokens=max_input_tokens())
