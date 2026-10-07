"""llm_service sends explicit options and reports truncation. Ollama is never
contacted: requests.post is replaced."""

import logging

import pytest
import requests

from app.config import (
    OLLAMA_MAX_OUTPUT_TOKENS,
    OLLAMA_NUM_CTX,
    OLLAMA_TEMPERATURE,
)
from app.services import llm_service


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.ok = status_code < 400

    def json(self):
        return self._payload


def reply(text="An answer.", **extra):
    return FakeResponse({"message": {"content": text}, **extra})


@pytest.fixture()
def post(monkeypatch):
    sent = {}

    def install(response):
        def fake_post(url, json=None, timeout=None):
            sent["url"], sent["json"], sent["timeout"] = url, json, timeout
            if isinstance(response, Exception):
                raise response
            return response

        monkeypatch.setattr(llm_service.requests, "post", fake_post)
        return sent

    return install


def test_context_window_temperature_and_output_cap_are_always_set(post):
    sent = post(reply())
    assert llm_service.generate("sys", "user").ok
    assert sent["json"]["options"] == {
        "num_ctx": OLLAMA_NUM_CTX,
        "temperature": OLLAMA_TEMPERATURE,
        "num_predict": OLLAMA_MAX_OUTPUT_TOKENS,
    }
    assert sent["json"]["stream"] is False


def test_temperature_and_output_cap_can_be_overridden_per_call(post):
    sent = post(reply())
    llm_service.generate("sys", "user", temperature=0.0, max_output_tokens=321)
    assert sent["json"]["options"]["temperature"] == 0.0  # zero is a real value, not "unset"
    assert sent["json"]["options"]["num_predict"] == 321
    assert sent["json"]["options"]["num_ctx"] == OLLAMA_NUM_CTX  # the window is not per-call


def test_json_mode_still_sets_the_format(post):
    sent = post(reply('{"a": 1}'))
    llm_service.generate("sys", "user", json_mode=True)
    assert sent["json"]["format"] == "json"


def test_the_system_prompt_is_the_first_message(post):
    sent = post(reply())
    llm_service.generate("RULES", "question")
    assert sent["json"]["messages"][0] == {"role": "system", "content": "RULES"}
    assert sent["json"]["messages"][1] == {"role": "user", "content": "question"}


def test_a_prompt_that_fills_the_window_is_logged_as_truncated(post, caplog):
    post(reply(prompt_eval_count=OLLAMA_NUM_CTX))
    with caplog.at_level(logging.WARNING, logger=llm_service.logger.name):
        result = llm_service.generate("sys", "user")
    assert result.ok and result.prompt_tokens == OLLAMA_NUM_CTX
    assert "truncated" in caplog.text


def test_a_prompt_with_room_to_spare_is_not_flagged(post, caplog):
    post(reply(prompt_eval_count=OLLAMA_NUM_CTX // 2))
    with caplog.at_level(logging.WARNING, logger=llm_service.logger.name):
        result = llm_service.generate("sys", "user")
    assert result.prompt_tokens == OLLAMA_NUM_CTX // 2
    assert caplog.text == ""


def test_a_prompt_over_the_budget_is_warned_about_before_it_is_sent(post, caplog):
    sent = post(reply())
    too_long = "x" * (OLLAMA_NUM_CTX * 10)
    with caplog.at_level(logging.WARNING, logger=llm_service.logger.name):
        result = llm_service.generate("sys", too_long)
    assert sent["json"]  # still sent: the warning is for the log, the builders are the fix
    assert result.ok
    assert "will truncate" in caplog.text


def test_a_prompt_within_the_budget_is_not_warned_about(post, caplog):
    post(reply())
    with caplog.at_level(logging.WARNING, logger=llm_service.logger.name):
        llm_service.generate("sys", "a normal question")
    assert caplog.text == ""


def test_the_budget_check_uses_the_per_call_output_cap(post, caplog):
    post(reply())
    prompt = "x" * 9000  # ~3000 tokens: fits with a small reply, not with a large one
    with caplog.at_level(logging.WARNING, logger=llm_service.logger.name):
        llm_service.generate("sys", prompt, max_output_tokens=100)
        assert caplog.text == ""
        llm_service.generate("sys", prompt, max_output_tokens=2000)
    assert "will truncate" in caplog.text


def test_a_reply_cut_by_the_output_cap_is_reported(post, caplog):
    post(reply("half an ans", done_reason="length"))
    with caplog.at_level(logging.WARNING, logger=llm_service.logger.name):
        result = llm_service.generate("sys", "user")
    assert result.ok and result.hit_output_limit is True
    assert "output token limit" in caplog.text


def test_a_normal_stop_is_not_a_cut_off(post):
    post(reply(done_reason="stop"))
    assert llm_service.generate("sys", "user").hit_output_limit is False


def test_missing_token_counts_are_tolerated(post):
    post(reply())
    assert llm_service.generate("sys", "user").prompt_tokens is None


@pytest.mark.parametrize(
    "response,expected",
    [
        (requests.exceptions.ConnectionError(), "not running"),
        (requests.exceptions.Timeout(), "timed out"),
        (FakeResponse(status_code=404), "not pulled"),
        (FakeResponse(status_code=500), "HTTP 500"),
        (FakeResponse({"unexpected": True}), "malformed"),
        (reply("   "), "empty"),
    ],
)
def test_failures_come_back_as_results_not_exceptions(post, response, expected):
    post(response)
    result = llm_service.generate("sys", "user")
    assert result.ok is False and expected in result.error
