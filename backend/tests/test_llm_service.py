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


@pytest.mark.parametrize("status,retryable", [(500, True), (502, True), (503, True), (404, False), (400, False)])
def test_only_an_error_inside_ollama_is_worth_retrying(post, status, retryable):
    post(FakeResponse(status_code=status))
    assert llm_service.generate("sys", "user").retryable is retryable


@pytest.mark.parametrize(
    "exc", [requests.exceptions.ConnectionError(), requests.exceptions.Timeout()]
)
def test_not_running_and_timeouts_are_not_retryable(post, exc):
    post(exc)
    assert llm_service.generate("sys", "user").retryable is False


# --- streaming -------------------------------------------------------------------------------

import json as _json  # noqa: E402


class FakeStream:
    """A streaming response: yields the given NDJSON lines, then optionally raises."""

    def __init__(self, lines, status_code=200, then_raise=None):
        self._lines = lines
        self.status_code = status_code
        self.ok = status_code < 400
        self._then_raise = then_raise
        self.closed = False

    def iter_lines(self):
        for line in self._lines:
            yield line if isinstance(line, bytes) else _json.dumps(line).encode()
        if self._then_raise:
            raise self._then_raise

    def close(self):
        self.closed = True


def chunk(text, **extra):
    return {"message": {"role": "assistant", "content": text}, "done": False, **extra}


DONE = {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop", "prompt_eval_count": 321}


@pytest.fixture()
def post_stream(monkeypatch):
    sent = {}

    def install(response):
        def fake_post(url, json=None, timeout=None, stream=False):
            sent.update(url=url, json=json, timeout=timeout, stream=stream)
            if isinstance(response, Exception):
                raise response
            sent["response"] = response
            return response

        monkeypatch.setattr(llm_service.requests, "post", fake_post)
        return sent

    return install


def run_stream(*args, **kwargs):
    events = list(llm_service.generate_stream(*args, **kwargs))
    tokens = [e[1] for e in events if e[0] == "token"]
    assert events[-1][0] == "end" and sum(e[0] == "end" for e in events) == 1
    return tokens, events[-1][1]


def test_tokens_arrive_in_order_then_one_end_with_the_whole_text(post_stream):
    sent = post_stream(FakeStream([chunk("Hel"), chunk("lo "), chunk("there"), DONE]))
    tokens, end = run_stream("sys", "user")
    assert tokens == ["Hel", "lo ", "there"]
    assert end.ok and end.text == "Hello there" and end.prompt_tokens == 321
    assert sent["stream"] is True and sent["json"]["stream"] is True
    assert sent["response"].closed  # the connection is released


def test_streaming_sets_the_same_explicit_options_as_the_blocking_call(post_stream):
    sent = post_stream(FakeStream([chunk("x"), DONE]))
    run_stream("sys", "user", temperature=0.0, max_output_tokens=77)
    assert sent["json"]["options"] == {"num_ctx": OLLAMA_NUM_CTX, "temperature": 0.0, "num_predict": 77}
    assert "format" not in sent["json"]


def test_the_wait_is_bounded_per_piece_not_for_the_whole_answer(post_stream):
    from app.config import OLLAMA_TIMEOUT_SECONDS

    sent = post_stream(FakeStream([chunk("x"), DONE]))
    run_stream("sys", "user")
    connect, read = sent["timeout"]
    assert read == OLLAMA_TIMEOUT_SECONDS and connect < read


def test_blank_keep_alive_lines_are_ignored(post_stream):
    post_stream(FakeStream([b"", chunk("a"), b"", DONE]))
    tokens, end = run_stream("sys", "user")
    assert tokens == ["a"] and end.ok


@pytest.mark.parametrize(
    "exc,expected",
    [
        (requests.exceptions.ConnectionError(), "not running"),
        (requests.exceptions.Timeout(), "timed out"),
    ],
)
def test_a_request_that_cannot_start_ends_with_a_readable_error(post_stream, exc, expected):
    post_stream(exc)
    tokens, end = run_stream("sys", "user")
    assert tokens == [] and end.ok is False and expected in end.error


@pytest.mark.parametrize("status,expected", [(404, "not pulled"), (500, "HTTP 500")])
def test_error_statuses_end_the_stream_without_tokens(post_stream, status, expected):
    sent = post_stream(FakeStream([], status_code=status))
    tokens, end = run_stream("sys", "user")
    assert tokens == [] and not end.ok and expected in end.error
    assert sent["response"].closed


def test_a_drop_part_way_keeps_what_arrived_and_says_why(post_stream):
    post_stream(FakeStream([chunk("Partial "), chunk("answer")], then_raise=requests.exceptions.ConnectionError()))
    tokens, end = run_stream("sys", "user")
    assert tokens == ["Partial ", "answer"]
    assert end.ok is False and end.text == "Partial answer" and "not running" in end.error


def test_a_timeout_between_pieces_keeps_the_partial_text(post_stream):
    post_stream(FakeStream([chunk("Some text")], then_raise=requests.exceptions.ReadTimeout()))
    _, end = run_stream("sys", "user")
    assert not end.ok and end.text == "Some text" and "timed out" in end.error


def test_a_stream_that_ends_without_done_is_an_interrupted_answer(post_stream):
    post_stream(FakeStream([chunk("cut"), chunk(" off")]))
    _, end = run_stream("sys", "user")
    assert not end.ok and end.text == "cut off" and "closed" in end.error


def test_an_error_line_from_ollama_ends_the_stream(post_stream):
    post_stream(FakeStream([chunk("a"), {"error": "model runner crashed"}]))
    tokens, end = run_stream("sys", "user")
    assert tokens == ["a"] and not end.ok and "model runner crashed" in end.error


@pytest.mark.parametrize("bad", [b"not json", b"[1, 2]"])
def test_malformed_lines_end_the_stream(post_stream, bad):
    post_stream(FakeStream([chunk("a"), bad, chunk("never")]))
    tokens, end = run_stream("sys", "user")
    assert tokens == ["a"] and not end.ok and "malformed" in end.error


def test_a_stream_with_no_text_is_an_empty_response(post_stream):
    post_stream(FakeStream([DONE]))
    tokens, end = run_stream("sys", "user")
    assert tokens == [] and not end.ok and "empty" in end.error


def test_hitting_the_output_cap_is_reported_on_the_end_event(post_stream):
    post_stream(FakeStream([chunk("text"), {**DONE, "done_reason": "length"}]))
    _, end = run_stream("sys", "user")
    assert end.ok and end.hit_output_limit is True


def test_closing_the_stream_early_closes_the_connection(post_stream):
    sent = post_stream(FakeStream([chunk("a"), chunk("b"), chunk("c"), DONE]))
    gen = llm_service.generate_stream("sys", "user")
    assert next(gen) == ("token", "a")
    gen.close()  # what happens when the browser goes away
    assert sent["response"].closed


# --- aborting a stream from another thread ----------------------------------------------------------


def test_aborting_before_the_connection_exists_closes_it_on_attach():
    abort = llm_service.StreamAbort()
    abort.abort()
    response = FakeStream([])
    abort.attach(response)
    assert abort.aborted and response.closed


def test_aborting_after_the_connection_exists_closes_it():
    abort = llm_service.StreamAbort()
    response = FakeStream([])
    abort.attach(response)
    assert not response.closed
    abort.abort()
    assert response.closed


def test_a_failing_close_does_not_raise_out_of_abort():
    class Unclosable(FakeStream):
        def close(self):
            raise OSError("already gone")

    abort = llm_service.StreamAbort()
    abort.attach(Unclosable([]))
    abort.abort()  # must not raise
    assert abort.aborted


def test_an_aborted_stream_ends_as_stopped_with_what_arrived(post_stream):
    abort = llm_service.StreamAbort()

    class AbortedMidRead(FakeStream):
        def iter_lines(self):
            yield _json.dumps(chunk("Some ")).encode()
            abort.abort()  # another thread stops the answer; the socket read then fails
            raise requests.exceptions.ConnectionError("connection closed")

    sent = post_stream(AbortedMidRead([]))
    events = list(llm_service.generate_stream("sys", "user", abort=abort))

    assert events[0] == ("token", "Some ")
    end = events[-1][1]
    assert end.ok is False and end.error == "Stopped." and end.text == "Some"
    assert sent["response"].closed


def test_an_abort_that_arrives_between_lines_still_ends_the_stream(post_stream):
    abort = llm_service.StreamAbort()

    class Lines(FakeStream):
        def iter_lines(self):
            yield _json.dumps(chunk("a")).encode()
            abort.abort()
            return  # the closed connection just ends the iteration

    post_stream(Lines([]))
    end = list(llm_service.generate_stream("sys", "user", abort=abort))[-1][1]
    assert end.ok is False and end.error == "Stopped."


def test_streaming_without_an_abort_handle_is_unchanged(post_stream):
    post_stream(FakeStream([chunk("x"), DONE]))
    _, end = run_stream("sys", "user")
    assert end.ok
