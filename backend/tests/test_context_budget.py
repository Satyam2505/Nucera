from app.services.context_budget import (
    CHARS_PER_TOKEN,
    TEMPLATE_OVERHEAD_TOKENS,
    estimate_tokens,
    prompt_token_budget,
    truncate_at_word,
    user_prompt_char_budget,
)


def test_estimate_rounds_up():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("a" * CHARS_PER_TOKEN) == 1
    assert estimate_tokens("a" * (CHARS_PER_TOKEN + 1)) == 2


def test_prompt_budget_leaves_room_for_the_reply_and_the_template():
    assert prompt_token_budget(1000, num_ctx=4096) == 4096 - 1000 - TEMPLATE_OVERHEAD_TOKENS
    assert prompt_token_budget(5000, num_ctx=4096) == 0  # never negative


def test_user_budget_is_what_the_system_prompt_leaves():
    system = "s" * 300  # 100 estimated tokens
    chars = user_prompt_char_budget(system, 1000, num_ctx=4096)
    assert chars == (4096 - 1000 - TEMPLATE_OVERHEAD_TOKENS - 100) * CHARS_PER_TOKEN
    assert user_prompt_char_budget("s" * 99999, 1000, num_ctx=4096) == 0


def test_the_whole_prompt_stays_in_the_window_at_the_budget():
    system = "rules " * 100
    user = "u" * user_prompt_char_budget(system, 1024, num_ctx=4096)
    assert estimate_tokens(system) + estimate_tokens(user) + 1024 + TEMPLATE_OVERHEAD_TOKENS <= 4096


def test_truncate_at_word():
    assert truncate_at_word("short", 50) == "short"
    cut = truncate_at_word("alpha beta gamma delta", 14)
    assert cut == "alpha beta…" and len(cut) <= 14
    assert truncate_at_word("x" * 100, 10) == "x" * 9 + "…"  # no word break to use
    assert truncate_at_word("anything", 1) == ""
