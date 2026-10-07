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

import json
import logging
import threading
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple, Union

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

# Seconds to wait for the connection when streaming; the read timeout is
# OLLAMA_TIMEOUT_SECONDS.
_CONNECT_TIMEOUT = 10


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
    # True for a failure worth trying once more: Ollama itself returned a 5xx
    # (it does so now and then, with no reason logged, and the same request
    # usually works the second time). Not set for "not running", "model not
    # pulled" or a timeout, where a retry would only double the wait.
    retryable: bool = False


class StreamAbort:
    """Lets another thread stop a generate_stream() that is blocked waiting for
    the model: closing the connection to Ollama makes it stop generating (which
    matters on a CPU, where an unwanted answer is minutes of work).

    The connection can only be closed once Ollama has sent its response headers,
    which for a streamed chat is about when the prompt has been read; an abort
    before that takes effect at that point.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._response = None
        self._aborted = False

    @property
    def aborted(self) -> bool:
        return self._aborted

    def attach(self, response) -> None:
        with self._lock:
            self._response = response
            aborted = self._aborted
        if aborted:
            response.close()

    def abort(self) -> None:
        with self._lock:
            self._aborted = True
            response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:  # closing is best effort; there is nothing to recover
                logger.debug("Closing the model connection failed", exc_info=True)


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


def _build_payload(
    system_prompt: str,
    user_prompt: str,
    model_name: str,
    stream: bool,
    json_mode: bool,
    temperature: Optional[float],
    output_tokens: int,
) -> dict:
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": stream,
        "options": {
            "num_ctx": OLLAMA_NUM_CTX,
            "temperature": OLLAMA_TEMPERATURE if temperature is None else temperature,
            "num_predict": output_tokens,
        },
    }
    if json_mode:
        payload["format"] = "json"
    return payload


def _request_error(exc: requests.exceptions.RequestException) -> str:
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Ollama is not running or unreachable."
    if isinstance(exc, requests.exceptions.Timeout):
        return "The local model timed out."
    return f"Request to the local model failed: {exc}"


def _status_error(response, model_name: str) -> Optional[str]:
    if response.status_code == 404:
        return f"Model '{model_name}' is not pulled in Ollama."
    if not response.ok:
        return f"Ollama returned HTTP {response.status_code}."
    return None


def _note_stats(data: dict) -> Tuple[Optional[int], bool]:
    """(prompt tokens, hit the output cap) from Ollama's final message, with the
    matching log warnings."""
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
    return prompt_tokens, hit_limit


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
    payload = _build_payload(
        system_prompt, user_prompt, model_name, False, json_mode, temperature, output_tokens
    )

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=timeout if timeout is not None else OLLAMA_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        return LLMResult(ok=False, error=_request_error(exc))

    error = _status_error(response, model_name)
    if error:
        return LLMResult(ok=False, error=error, retryable=response.status_code >= 500)

    try:
        data = response.json()
        text = data["message"]["content"]
    except (ValueError, KeyError, TypeError):
        return LLMResult(ok=False, error="Ollama returned a malformed response.")

    if not text or not text.strip():
        return LLMResult(ok=False, error="The local model returned an empty response.")

    prompt_tokens, hit_limit = _note_stats(data)
    return LLMResult(
        ok=True, text=text.strip(), prompt_tokens=prompt_tokens, hit_output_limit=hit_limit
    )


def generate_stream(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    abort: Optional[StreamAbort] = None,
) -> Iterator[Tuple[str, Union[str, LLMResult]]]:
    """Like generate(), but yields ("token", text) as the model writes and ends
    with exactly one ("end", LLMResult). Never raises.

    The result's text is everything streamed. If the connection drops part-way
    the result has ok=False with the partial text and the reason, so the caller
    can keep what arrived. Here OLLAMA_TIMEOUT_SECONDS bounds the wait for each
    piece (the first one is slow: it follows reading the whole prompt), not the
    whole answer, so a long answer that keeps flowing never times out.
    Closing the generator early closes the connection, which stops Ollama; so
    does `abort.abort()` from another thread, in which case the result is an
    ok=False "stopped" with whatever had arrived.
    """
    model_name = model or OLLAMA_MODEL
    output_tokens = OLLAMA_MAX_OUTPUT_TOKENS if max_output_tokens is None else max_output_tokens
    _warn_if_over_budget(system_prompt, user_prompt, output_tokens)
    payload = _build_payload(
        system_prompt, user_prompt, model_name, True, False, temperature, output_tokens
    )

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=(_CONNECT_TIMEOUT, OLLAMA_TIMEOUT_SECONDS),
            stream=True,
        )
    except requests.exceptions.RequestException as exc:
        yield "end", LLMResult(ok=False, error=_request_error(exc))
        return

    if abort is not None:
        abort.attach(response)

    parts: List[str] = []
    error: Optional[str] = _status_error(response, model_name)
    final: dict = {}
    try:
        if error is None:
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    error = "Ollama returned a malformed response."
                    break
                if not isinstance(data, dict):
                    error = "Ollama returned a malformed response."
                    break
                if data.get("error"):
                    error = f"The local model reported an error: {data['error']}"
                    break
                message = data.get("message")
                piece = message.get("content") if isinstance(message, dict) else None
                if piece:
                    parts.append(piece)
                    yield "token", piece
                if data.get("done"):
                    final = data
                    break
            else:
                if not final:
                    error = "The connection to the local model closed before the answer finished."
    except (requests.exceptions.RequestException, OSError, ValueError) as exc:
        # An abort closes the connection under the read, which surfaces as one of these.
        error = "Stopped." if abort is not None and abort.aborted else (
            _request_error(exc) if isinstance(exc, requests.exceptions.RequestException) else str(exc)
        )
    finally:
        response.close()

    if abort is not None and abort.aborted and not final:
        error = "Stopped."
    text = "".join(parts)
    if error is None and not text.strip():
        error = "The local model returned an empty response."
    prompt_tokens, hit_limit = _note_stats(final) if final else (None, False)
    yield "end", LLMResult(
        ok=error is None,
        text=text.strip(),
        error=error,
        prompt_tokens=prompt_tokens,
        hit_output_limit=hit_limit,
    )
