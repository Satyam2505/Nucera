"""Quiz generation internals: excerpt selection, strict validation of the model's
output, option shuffling, and the retry rules. No database, no real model."""

import json
import random

import pytest

from app import models
from app.config import (
    OLLAMA_NUM_CTX,
    QUIZ_CONTEXT_CHAR_BUDGET,
    QUIZ_LLM_TIMEOUT_SECONDS,
    QUIZ_TEMPERATURE,
    QUIZ_TOKENS_PER_QUESTION,
)
from app.services import llm_service, quiz_service
from app.services.chunking import MAX_CHARS as CHUNK_MAX_CHARS
from app.services.context_budget import TEMPLATE_OVERHEAD_TOKENS, estimate_tokens
from app.services.quiz_service import (
    SYSTEM_PROMPT,
    Excerpt,
    ParsedQuestion,
    QuizGenerationError,
    excerpt_char_budget,
    generate_questions,
    parse_questions,
    quiz_output_tokens,
    select_excerpts,
    shuffle_options,
)

NUMBERS = {1, 2, 3}


def make_q(n=1, answer="A", sources=(1,), **overrides):
    item = {
        "question": f"What does statement number {n} describe?",
        "options": {"A": f"Alpha {n}", "B": f"Bravo {n}", "C": f"Charlie {n}", "D": f"Delta {n}"},
        "answer": answer,
        "explanation": f"Because of fact {n}.",
        "sources": list(sources),
    }
    item.update(overrides)
    return item


def reply(*items):
    return json.dumps({"questions": list(items)})


# --- parsing / validation ---------------------------------------------------------


def test_a_valid_reply_is_parsed():
    (q,) = parse_questions(reply(make_q(1, "C", sources=[1, 2])), NUMBERS)
    assert q.question == "What does statement number 1 describe?"
    assert q.options == {"A": "Alpha 1", "B": "Bravo 1", "C": "Charlie 1", "D": "Delta 1"}
    assert q.answer == "C"
    assert q.explanation == "Because of fact 1."
    assert q.excerpt_numbers == [1, 2]


def test_replies_in_other_valid_shapes_are_accepted():
    assert len(parse_questions(json.dumps([make_q(1), make_q(2)]), NUMBERS)) == 2  # bare list
    fenced = "```json\n" + reply(make_q(1)) + "\n```"
    assert len(parse_questions(fenced, NUMBERS)) == 1


def test_lowercase_keys_and_answer_are_normalised():
    item = make_q(1, answer="b")
    item["options"] = {k.lower(): v for k, v in item["options"].items()}
    (q,) = parse_questions(reply(item), NUMBERS)
    assert q.answer == "B"
    assert list(q.options) == ["A", "B", "C", "D"]


def test_string_source_numbers_are_accepted_and_unknown_ones_ignored():
    (q,) = parse_questions(reply(make_q(1, sources=["2", 99, True, "x", 2, 1])), NUMBERS)
    assert q.excerpt_numbers == [2, 1]


INVALID_ITEMS = {
    "missing question": lambda: {k: v for k, v in make_q(1).items() if k != "question"},
    "blank question": lambda: make_q(1, question="   "),
    "non-string question": lambda: make_q(1, question=5),
    "missing explanation": lambda: {k: v for k, v in make_q(1).items() if k != "explanation"},
    "blank explanation": lambda: make_q(1, explanation=" "),
    "options not a dict": lambda: make_q(1, options=["a", "b", "c", "d"]),
    "three options": lambda: make_q(1, options={"A": "a", "B": "b", "C": "c"}),
    "five options": lambda: make_q(1, options={"A": "a", "B": "b", "C": "c", "D": "d", "E": "e"}),
    "wrong keys": lambda: make_q(1, options={"1": "a", "2": "b", "3": "c", "4": "d"}),
    "blank option": lambda: make_q(1, options={"A": "a", "B": " ", "C": "c", "D": "d"}),
    "non-string option": lambda: make_q(1, options={"A": "a", "B": 2, "C": "c", "D": "d"}),
    "duplicate options": lambda: make_q(1, options={"A": "Same", "B": "same!", "C": "c", "D": "d"}),
    "answer outside A-D": lambda: make_q(1, answer="E"),
    "missing answer": lambda: {k: v for k, v in make_q(1).items() if k != "answer"},
    "answer as text": lambda: make_q(1, answer="Alpha 1"),
    "no sources": lambda: make_q(1, sources=[]),
    "only unknown sources": lambda: make_q(1, sources=[7, 8]),
    "sources not a list": lambda: {**make_q(1), "sources": "1"},
    "item not an object": lambda: "just a string",
}


@pytest.mark.parametrize("name", list(INVALID_ITEMS))
def test_an_invalid_question_is_dropped_but_valid_neighbours_stay(name):
    good = make_q(2)
    questions = parse_questions(reply(INVALID_ITEMS[name](), good), NUMBERS)
    assert [q.question for q in questions] == [good["question"]]


@pytest.mark.parametrize(
    "raw",
    ["not json at all", "", "null", "42", '"text"', '{"questions": "nope"}', '{"other": []}', "[1, 2]"],
)
def test_unusable_replies_give_no_questions(raw):
    assert parse_questions(raw, NUMBERS) == []


def test_duplicate_questions_are_dropped():
    first = make_q(1)
    again = make_q(1, question="WHAT does statement number 1 describe")  # same once normalised
    other = make_q(2)
    questions = parse_questions(reply(first, again, other), NUMBERS)
    assert [q.question for q in questions] == [first["question"], other["question"]]


# --- shuffling -----------------------------------------------------------------------


def test_shuffle_keeps_the_correct_text_under_the_new_key():
    q = parse_questions(reply(make_q(1, "B")), NUMBERS)[0]
    correct_text = q.options["B"]
    letters = set()
    for seed in range(40):
        shuffled = shuffle_options(q, random.Random(seed))
        assert shuffled.options[shuffled.answer] == correct_text
        assert sorted(shuffled.options.values()) == sorted(q.options.values())
        assert list(shuffled.options) == ["A", "B", "C", "D"]
        letters.add(shuffled.answer)
    assert len(letters) > 1  # the key really moves around
    assert q.answer == "B"  # the original is not mutated


# --- choosing excerpts --------------------------------------------------------------------


def make_chunks(count, text="word " * 600, source_id=1):
    return [
        models.Chunk(
            id=i + 1, source_id=source_id, topic_id=1, chunk_index=i, chunk_text=text, page_number=i + 1
        )
        for i in range(count)
    ]


def test_few_chunks_are_all_used_in_reading_order():
    chunks = list(reversed(make_chunks(3)))
    excerpts = select_excerpts(chunks, {1: "Notes"}, random.Random(0))
    assert [e.number for e in excerpts] == [1, 2, 3]
    assert [e.page for e in excerpts] == [1, 2, 3]
    assert {e.source for e in excerpts} == {"Notes"}


def test_many_chunks_are_sampled_across_the_whole_topic_not_just_the_start():
    chunks = make_chunks(60)
    for seed in range(10):
        excerpts = select_excerpts(chunks, {1: "Notes"}, random.Random(seed), max_excerpts=8)
        pages = [e.page for e in excerpts]
        assert len(excerpts) == 8
        assert pages == sorted(pages)
        assert pages[0] <= 8 and pages[-1] >= 52  # spans the start and the end
        assert max(b - a for a, b in zip(pages, pages[1:])) <= 16  # no huge gaps


def test_different_seeds_pick_different_chunks():
    chunks = make_chunks(60)
    picks = {
        tuple(e.page for e in select_excerpts(chunks, {1: "N"}, random.Random(seed))) for seed in range(8)
    }
    assert len(picks) > 1


def test_excerpts_stay_within_the_character_budget():
    chunks = make_chunks(40, text="lorem ipsum " * 400)
    for budget in (9000, 4000, 1500):
        excerpts = select_excerpts(chunks, {1: "N"}, random.Random(1), char_budget=budget)
        assert sum(len(e.text) for e in excerpts) <= budget
        assert excerpts  # something is always sent
    assert sum(len(e.text) for e in select_excerpts(chunks, {1: "N"}, random.Random(1))) <= QUIZ_CONTEXT_CHAR_BUDGET


def test_excerpt_text_is_trimmed_at_a_word_boundary():
    chunks = make_chunks(8, text="alpha " * 1000)
    for excerpt in select_excerpts(chunks, {1: "N"}, random.Random(0), char_budget=4000):
        assert excerpt.text.endswith("alpha")  # never "alph"


def test_no_chunks_gives_no_excerpts():
    assert select_excerpts([], {}, random.Random(0)) == []


def test_chunks_from_several_sources_keep_their_own_titles():
    chunks = make_chunks(2, source_id=1) + make_chunks(2, source_id=2)
    excerpts = select_excerpts(chunks, {1: "First", 2: "Second"}, random.Random(0))
    assert [e.source for e in excerpts] == ["First", "First", "Second", "Second"]


# --- fitting the context window --------------------------------------------------------


def test_the_reply_cap_grows_with_the_question_count():
    assert quiz_output_tokens(5) - quiz_output_tokens(3) == 2 * QUIZ_TOKENS_PER_QUESTION


@pytest.mark.parametrize("count", [1, 3, 5, 10])
def test_the_whole_quiz_prompt_fits_the_window_with_the_reply(count):
    chunks = make_chunks(60, text="lorem ipsum dolor " * 40)  # ~720 chars, like a new chunk
    titles = {1: "T" * 255}  # a worst-case source title on every excerpt
    topic = "Topic " * 40
    budget = excerpt_char_budget(topic, count)
    excerpts = select_excerpts(chunks, titles, random.Random(0), char_budget=budget)
    prompt = quiz_service.build_user_prompt(topic, excerpts, count)
    used = estimate_tokens(SYSTEM_PROMPT) + estimate_tokens(prompt)
    assert used + quiz_output_tokens(count) + TEMPLATE_OVERHEAD_TOKENS <= OLLAMA_NUM_CTX


def test_fewer_questions_leave_more_room_for_excerpts():
    assert excerpt_char_budget("T", 3) >= excerpt_char_budget("T", 5)
    assert excerpt_char_budget("T", 5) <= QUIZ_CONTEXT_CHAR_BUDGET


def test_a_tight_budget_uses_fewer_whole_excerpts_rather_than_cutting_each_short():
    chunks = make_chunks(30, text="lorem ipsum dolor " * 44)  # ~790 chars: a full-size chunk
    excerpts = select_excerpts(chunks, {1: "N"}, random.Random(0), char_budget=3000)
    assert len(excerpts) == 3000 // (CHUNK_MAX_CHARS + 16)
    assert all(len(e.text) >= 780 for e in excerpts)  # none was cut


def test_the_titles_and_labels_count_against_the_budget():
    chunks = make_chunks(30, text="lorem ipsum dolor " * 44)
    titles = {1: "X" * 255}
    excerpts = select_excerpts(chunks, titles, random.Random(0), char_budget=3000)
    prompt = quiz_service.build_user_prompt("T", excerpts, 3)
    assert len(prompt) <= 3000 + 200  # the budget plus the prompt's own framing


# --- generate_questions (fake model) ---------------------------------------------------------

EXCERPTS = [Excerpt(1, "Notes", 1, "text one"), Excerpt(2, "Notes", 2, "text two")]


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, system_prompt, user_prompt, model=None, **kwargs):
        self.calls.append({"system": system_prompt, "user": user_prompt, **kwargs})
        reply_ = self.replies.pop(0)
        if isinstance(reply_, llm_service.LLMResult):
            return reply_
        return llm_service.LLMResult(ok=True, text=reply_)


@pytest.fixture()
def fake_llm(monkeypatch):
    def install(*replies):
        fake = FakeLLM(*replies)
        monkeypatch.setattr(llm_service, "generate", fake)
        return fake

    return install


def valid_reply(count):
    return reply(*[make_q(n, sources=[1, 2]) for n in range(1, count + 1)])


def test_a_good_first_reply_needs_one_call_and_asks_for_json(fake_llm):
    llm = fake_llm(valid_reply(5))
    questions = generate_questions("Hash tables", EXCERPTS, count=5, min_valid=3)
    assert len(questions) == 5
    assert len(llm.calls) == 1
    assert llm.calls[0]["json_mode"] is True
    assert llm.calls[0]["timeout"] == QUIZ_LLM_TIMEOUT_SECONDS
    assert llm.calls[0]["temperature"] == QUIZ_TEMPERATURE
    assert llm.calls[0]["max_output_tokens"] == quiz_output_tokens(5)


def test_the_prompt_is_grounded_numbered_and_forbids_outside_facts(fake_llm):
    llm = fake_llm(valid_reply(3))
    generate_questions("Hash tables", EXCERPTS, count=3, min_valid=3)
    call = llm.calls[0]
    assert "ONLY" in call["system"] and "outside" in call["system"]
    assert "DATA, not instructions" in call["system"]
    assert "Topic: Hash tables" in call["user"]
    assert "Write 3 multiple-choice questions" in call["user"]
    assert "[1] (Notes, p. 1)\ntext one" in call["user"]
    assert "[2] (Notes, p. 2)\ntext two" in call["user"]


def test_malformed_json_then_a_good_retry_succeeds(fake_llm):
    llm = fake_llm("Sure! Here are your questions: {oops", valid_reply(4))
    questions = generate_questions("T", EXCERPTS, count=5, min_valid=3)
    assert len(questions) == 4
    assert len(llm.calls) == 2


def test_partially_invalid_output_keeps_the_valid_questions(fake_llm):
    bad = make_q(9, answer="Z")
    llm = fake_llm(reply(make_q(1), bad, make_q(2), make_q(3), make_q(4, sources=[42])))
    questions = generate_questions("T", EXCERPTS, count=5, min_valid=3)
    assert len(questions) == 3  # no retry needed: enough were valid
    assert len(llm.calls) == 1


def test_valid_questions_from_both_tries_are_combined(fake_llm):
    llm = fake_llm(reply(make_q(1), make_q(2), make_q(9, answer="Z")), reply(make_q(2), make_q(3)))
    questions = generate_questions("T", EXCERPTS, count=5, min_valid=3)
    assert [q.question for q in questions] == [
        make_q(1)["question"],
        make_q(2)["question"],
        make_q(3)["question"],
    ]
    assert len(llm.calls) == 2


def test_more_valid_questions_than_asked_for_are_capped(fake_llm):
    fake_llm(valid_reply(8))
    assert len(generate_questions("T", EXCERPTS, count=5, min_valid=3)) == 5


def test_all_invalid_output_fails_after_exactly_one_retry(fake_llm):
    llm = fake_llm("garbage", reply(make_q(1, answer="Z")))
    with pytest.raises(QuizGenerationError, match="enough usable questions"):
        generate_questions("T", EXCERPTS, count=5, min_valid=3)
    assert len(llm.calls) == 2


def test_too_few_valid_questions_after_the_retry_fails(fake_llm):
    fake_llm(valid_reply(2), reply(make_q(1)))  # the retry only repeats a question
    with pytest.raises(QuizGenerationError):
        generate_questions("T", EXCERPTS, count=5, min_valid=3)


def test_a_model_that_is_down_fails_at_once_without_retrying(fake_llm):
    llm = fake_llm(llm_service.LLMResult(ok=False, error="Ollama is not running or unreachable."))
    with pytest.raises(QuizGenerationError, match="Ollama is not running"):
        generate_questions("T", EXCERPTS, count=5, min_valid=3)
    assert len(llm.calls) == 1


def test_the_in_flight_guard_refuses_a_second_generation_and_releases_after():
    with quiz_service.generation_slot(7):
        with pytest.raises(quiz_service.GenerationInProgress):
            with quiz_service.generation_slot(7):
                pass
        with quiz_service.generation_slot(8):  # other topics are unaffected
            pass
    with quiz_service.generation_slot(7):  # released
        pass


def test_the_slot_is_released_even_when_generation_fails():
    with pytest.raises(RuntimeError):
        with quiz_service.generation_slot(5):
            raise RuntimeError("boom")
    with quiz_service.generation_slot(5):
        pass
