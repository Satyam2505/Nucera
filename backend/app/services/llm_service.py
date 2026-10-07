"""Local LLM inference via Ollama.

Isolated behind generate() so the model/provider can be swapped later (a
different local model, a different local serving tool) without touching
the tutor prompt-building logic or the /ask route. Uses the plain HTTP API
(no extra dependency needed — `requests` is already pulled in transitively
by sentence-transformers).

Never raises. Every failure mode (Ollama not running, model not pulled,
timeout, malformed response) comes back as LLMResult(ok=False, error=...)
so the caller can degrade gracefully instead of crashing.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests

from app.config import (
    OLLAMA_BASE_URL,
    OLLAMA_MAX_OUTPUT_TOKENS,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT_SECONDS,
)
from app.services.context_budget import estimate_tokens, prompt_token_budget

logger = logging.getLogger(__name__)

# Ollama reports how many prompt tokens it actually processed. At or above this
# share of the window the prompt was probably cut. This is only a backstop:
# Ollama cuts an oversized prompt down to about half the window, so the count it
# reports afterwards is *below* this. The reliable check is the one made before
# sending (see _warn_if_over_budget).
_NEAR_FULL_WINDOW = 0.98


@dataclass
class LLMResult:
    ok: bool
    text: str = ""
    error: Optional[str] = None
    # Prompt tokens as counted by Ollama (None if it didn't say).
    prompt_tokens: Optional[int] = None
    # True when the reply stopped because it hit the output cap, not because
    # the model finished.
    hit_output_limit: bool = False


def _warn_if_over_budget(system_prompt: str, user_prompt: str, output_tokens: int) -> None:
    """The prompt builders keep prompts within the window; if one didn't, say so
    before Ollama quietly cuts the prompt. Ollama keeps only the first few
    tokens when it truncates, so it is the system prompt's grounding rules that
    would be lost."""
    estimated = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)
    budget = prompt_token_budget(output_tokens)
    if estimated > budget:
        logger.warning(
            "Prompt is about %d tokens but only %d fit the %d-token window alongside a "
            "%d-token reply; Ollama will truncate it and the system prompt's rules may be lost.",
            estimated,
            budget,
            OLLAMA_NUM_CTX,
            output_tokens,
        )


def generate(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    json_mode: bool = False,
    timeout: Optional[float] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
) -> LLMResult:
    """`json_mode` asks Ollama to constrain the reply to valid JSON (the shape
    is still up to the caller to validate). `timeout` overrides the default
    for callers whose generations are longer than a chat answer.

    The context window is always set explicitly (OLLAMA_NUM_CTX), never left to
    Ollama's default; temperature and the reply length cap default to the
    tutor's settings and can be overridden per call.
    """
    model_name = model or OLLAMA_MODEL
    output_tokens = OLLAMA_MAX_OUTPUT_TOKENS if max_output_tokens is None else max_output_tokens
    _warn_if_over_budget(system_prompt, user_prompt, output_tokens)

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "num_ctx": OLLAMA_NUM_CTX,
            "temperature": OLLAMA_TEMPERATURE if temperature is None else temperature,
            "num_predict": output_tokens,
        },
    }
    if json_mode:
        payload["format"] = "json"

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=timeout if timeout is not None else OLLAMA_TIMEOUT_SECONDS,
        )
    except requests.exceptions.ConnectionError:
        return LLMResult(ok=False, error="Ollama is not running or unreachable.")
    except requests.exceptions.Timeout:
        return LLMResult(ok=False, error="The local model timed out.")
    except requests.exceptions.RequestException as exc:
        return LLMResult(ok=False, error=f"Request to the local model failed: {exc}")

    if response.status_code == 404:
        return LLMResult(ok=False, error=f"Model '{model_name}' is not pulled in Ollama.")
    if not response.ok:
        return LLMResult(ok=False, error=f"Ollama returned HTTP {response.status_code}.")

    try:
        data = response.json()
        text = data["message"]["content"]
    except (ValueError, KeyError, TypeError):
        return LLMResult(ok=False, error="Ollama returned a malformed response.")

    if not text or not text.strip():
        return LLMResult(ok=False, error="The local model returned an empty response.")

    prompt_tokens = data.get("prompt_eval_count")
    if not isinstance(prompt_tokens, int):
        prompt_tokens = None
    if prompt_tokens is not None and prompt_tokens >= OLLAMA_NUM_CTX * _NEAR_FULL_WINDOW:
        logger.warning(
            "Ollama processed %d prompt tokens against a %d-token window: the prompt "
            "was probably truncated. Lower the prompt size or raise OLLAMA_NUM_CTX.",
            prompt_tokens,
            OLLAMA_NUM_CTX,
        )
    hit_limit = data.get("done_reason") == "length"
    if hit_limit:
        logger.warning("The local model's reply was cut off at the output token limit.")

    return LLMResult(
        ok=True, text=text.strip(), prompt_tokens=prompt_tokens, hit_output_limit=hit_limit
    )
