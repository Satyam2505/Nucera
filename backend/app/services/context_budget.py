"""Keeping prompts inside the local model's context window.

Ollama runs the model with a fixed window (OLLAMA_NUM_CTX) shared by the
prompt and the reply. A prompt that doesn't fit is cut from the front, which
is where the grounding rules live, so the prompt builders size what they send
to this budget instead of hoping it fits.

There is no Llama tokenizer in this project (and none is added: it would be a
new dependency for a safety margin), so lengths are estimated from characters.
The estimate is pessimistic on purpose, and llm_service logs a warning when
Ollama reports a prompt that came close to the window anyway.
"""

import math
from typing import Optional

from app.config import OLLAMA_NUM_CTX

# English prose is about 4 characters per token with Llama's tokenizer; maths,
# code and non-English text are denser, up to 2-3. Budgeting at 3 leaves room
# for the dense cases at the cost of using a little less of the window on prose.
CHARS_PER_TOKEN = 3

# The chat template wraps each message in role markers.
TEMPLATE_OVERHEAD_TOKENS = 64


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def prompt_token_budget(output_tokens: int, num_ctx: Optional[int] = None) -> int:
    """Tokens left for the whole prompt (system + user) once room for the
    reply and the chat template is kept free."""
    window = num_ctx if num_ctx is not None else OLLAMA_NUM_CTX
    return max(0, window - output_tokens - TEMPLATE_OVERHEAD_TOKENS)


def user_prompt_char_budget(
    system_prompt: str, output_tokens: int, num_ctx: Optional[int] = None
) -> int:
    """Characters the user message may use, given the system prompt that
    travels with it and the room kept free for the reply."""
    tokens = prompt_token_budget(output_tokens, num_ctx) - estimate_tokens(system_prompt)
    return max(0, tokens) * CHARS_PER_TOKEN


def truncate_at_word(text: str, limit: int) -> str:
    """`text` cut to at most `limit` characters at a word boundary, with an
    ellipsis when anything was removed."""
    text = text.strip()
    if len(text) <= limit:
        return text
    if limit <= 1:
        return ""
    cut = text[: limit - 1]
    boundary = cut.rfind(" ")
    if boundary > (limit - 1) // 2:
        cut = cut[:boundary]
    return cut.rstrip() + "…"
