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

from dataclasses import dataclass
from typing import Optional

import requests

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS


@dataclass
class LLMResult:
    ok: bool
    text: str = ""
    error: Optional[str] = None


def generate(system_prompt: str, user_prompt: str, model: Optional[str] = None) -> LLMResult:
    model_name = model or OLLAMA_MODEL

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
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

    return LLMResult(ok=True, text=text.strip())
