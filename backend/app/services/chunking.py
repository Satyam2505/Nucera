def chunk_text(text: str, max_chunk_size: int = 500) -> list[str]:
    """Simple paragraph-based chunking with a fixed-size fallback for long paragraphs."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs and text.strip():
        paragraphs = [text.strip()]

    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chunk_size:
            chunks.append(paragraph)
            continue
        for start in range(0, len(paragraph), max_chunk_size):
            chunks.append(paragraph[start : start + max_chunk_size])

    return chunks
