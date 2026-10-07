"""The mastery memory model (services/mastery_model.py), checked against numbers worked
out by hand from the formulas in its docstring. No database."""

import math
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import mastery_model as m

T0 = datetime(2026, 10, 1, 12, 0, 0)


def row(estimate=0.0, stability=3.0, reviewed=None, status="in_progress"):
    return SimpleNamespace(estimate=estimate, stability_days=stability, last_reviewed_at=reviewed, status=status)


def days(n):
    return T0 + timedelta(days=n)


# --- retrievability and the score shown -------------------------------------------------------------


def test_a_row_with_no_review_history_has_nothing_faded():
    assert m.is_tracked(row()) is False
    assert m.retrievability(row(estimate=0.9), days(100)) == 1.0


def test_memory_halves_every_stability_period():
    r = row(estimate=1.0, stability=3.0, reviewed=T0)
    assert m.retrievability(r, days(0)) == 1.0
    assert m.retrievability(r, days(3)) == pytest.approx(0.5)
    assert m.retrievability(r, days(6)) == pytest.approx(0.25)
    assert m.retrievability(r, days(1.5)) == pytest.approx(0.5 ** 0.5)


def test_the_clock_never_runs_backwards():
    assert m.retrievability(row(estimate=1, reviewed=days(5)), T0) == 1.0


def test_the_worked_example_from_the_proposal_50_then_25_then_about_10():
    r = row(estimate=0.5, stability=3.0, reviewed=T0)
    assert m.effective_score(r, days(0)) == 50
    assert m.effective_score(r, days(3)) == 25
    assert m.effective_score(r, days(7)) == 10  # 100 * 0.5 * 0.5**(7/3) = 9.92


def test_score_is_clamped_and_rounded_to_a_whole_number():
    assert m.effective_score(row(estimate=1.0, reviewed=T0), T0) == 100
    assert m.effective_score(row(estimate=0.0, reviewed=T0), T0) == 0
    assert m.effective_score(row(estimate=0.456, reviewed=T0), T0) == 46


def test_a_stability_below_the_minimum_is_treated_as_the_minimum():
    r = row(estimate=1.0, stability=0.25, reviewed=T0)
    assert m.retrievability(r, days(1)) == pytest.approx(0.5)  # half-life of the 1-day minimum
    # A missing or zero half-life means "not set": the 3-day default applies.
    assert m.retrievability(row(estimate=1.0, stability=0.0, reviewed=T0), days(3)) == pytest.approx(0.5)


# --- when a topic is due -------------------------------------------------------------------------------


def test_a_topic_is_due_once_retrievability_drops_below_eighty_percent():
    r = row(estimate=0.5, stability=3.0, reviewed=T0)
    due_after = 3.0 * math.log2(1 / 0.8)  # 0.966 days
    assert m.is_due_for_review(r, days(due_after - 0.05)) is False
    assert m.is_due_for_review(r, days(due_after + 0.05)) is True


def test_nothing_is_due_that_was_never_learned_or_never_reviewed():
    assert m.is_due_for_review(row(estimate=0.0, reviewed=T0), days(30)) is False
    assert m.is_due_for_review(row(estimate=0.9), days(30)) is False


def test_days_overdue_counts_from_the_moment_it_became_due():
    r = row(estimate=0.5, stability=3.0, reviewed=T0)
    due_after = 3.0 * math.log2(1 / 0.8)
    assert m.days_overdue(r, days(0.5)) == 0.0
    assert m.days_overdue(r, days(2)) == pytest.approx(2 - due_after)
    assert m.days_overdue(row(estimate=0.5), days(9)) == 0.0  # no history


# --- what a quiz does ------------------------------------------------------------------------------------


@pytest.mark.parametrize("n,weight", [(1, 0.25), (3, 0.5), (5, 0.625), (10, 10 / 13)])
def test_a_longer_quiz_is_more_evidence(n, weight):
    assert m.quiz_weight(n) == pytest.approx(weight)


def test_a_first_quiz_all_right_gives_half_of_the_evidence_it_can():
    estimate, stability = m.after_quiz(row(), correct=3, total=3, now=T0)
    assert estimate == pytest.approx(0.5) and stability == 3.0  # the proposal's worked example


def test_one_lucky_answer_barely_moves_a_new_topic_but_five_do_more():
    one, _ = m.after_quiz(row(), 1, 1, T0)
    five, _ = m.after_quiz(row(), 5, 5, T0)
    assert one == pytest.approx(0.25) and five == pytest.approx(0.625)


def test_reviewing_a_faded_topic_lengthens_its_memory_the_worked_example():
    # Reviewed 3 days ago (half faded), now 3 of 3: estimate 0.5 -> 0.75, stability 3 -> 5.25.
    r = row(estimate=0.5, stability=3.0, reviewed=T0)
    estimate, stability = m.after_quiz(r, 3, 3, days(3))
    assert estimate == pytest.approx(0.75)
    assert stability == pytest.approx(3.0 * (1 + 1.5 * 1.0 * (1 - 0.5)))  # 5.25


def test_reviewing_something_not_yet_faded_adds_no_stability():
    r = row(estimate=0.5, stability=3.0, reviewed=T0)
    _, stability = m.after_quiz(r, 3, 3, T0)  # retrievability still 1
    assert stability == pytest.approx(3.0)


def test_a_partial_pass_lengthens_in_proportion_to_the_fraction_right():
    r = row(estimate=0.5, stability=4.0, reviewed=T0)
    _, stability = m.after_quiz(r, 2, 3, days(4))  # 2/3 right, retrievability 0.5
    assert stability == pytest.approx(4.0 * (1 + 1.5 * (2 / 3) * 0.5))


def test_a_failed_quiz_shortens_the_memory_but_never_below_a_day():
    r = row(estimate=0.8, stability=10.0, reviewed=T0)
    _, stability = m.after_quiz(r, 1, 3, days(2))  # 1/3 < 0.6: a fail
    assert stability == pytest.approx(6.0)
    _, floor = m.after_quiz(row(estimate=0.8, stability=1.2, reviewed=T0), 0, 3, days(1))
    assert floor == m.MIN_STABILITY_DAYS


def test_a_failed_quiz_pulls_the_estimate_down_by_its_weight():
    r = row(estimate=0.8, stability=10.0, reviewed=T0)
    estimate, _ = m.after_quiz(r, 0, 3, T0)
    assert estimate == pytest.approx(0.5 * 0.8 + 0.5 * 0.0)


def test_the_estimate_stays_between_zero_and_one():
    assert m.after_quiz(row(estimate=1.0, reviewed=T0), 5, 5, T0)[0] == pytest.approx(1.0)
    assert m.after_quiz(row(estimate=0.0, reviewed=T0), 0, 5, T0)[0] == pytest.approx(0.0)


# --- editing the number by hand --------------------------------------------------------------------------------


def test_a_manual_adjustment_targets_the_score_shown_now():
    r = row(estimate=0.5, stability=3.0, reviewed=T0)  # at 3 days: remaining 0.5, shown 25
    assert m.estimate_for_effective_score(r, 35, days(3)) == pytest.approx(0.7)
    assert m.effective_score(SimpleNamespace(**{**r.__dict__, "estimate": 0.7}), days(3)) == 35


def test_a_faded_topic_cannot_be_pushed_above_what_its_memory_allows():
    r = row(estimate=0.5, stability=3.0, reviewed=T0)
    assert m.estimate_for_effective_score(r, 80, days(3)) == 1.0  # would need 1.6
    assert m.estimate_for_effective_score(r, 0, days(3)) == 0.0


# --- the score and status a loaded row shows ----------------------------------------------------------------


def test_an_untracked_row_is_left_exactly_as_stored():
    assert m.refreshed_fields(row(estimate=0.9)) is None


@pytest.mark.parametrize(
    "estimate,age_days,expected",
    [
        (0.9, 0, (90, "mastered")),
        (0.9, 3, (45, "in_progress")),  # faded from mastered to in progress
        (0.85, 0, (85, "mastered")),
        (0.8, 0, (80, "mastered")),
        (0.79, 0, (79, "in_progress")),
        (0.003, 0, (0, "unmastered")),
        (0.9, 60, (0, "unmastered")),  # long forgotten
    ],
)
def test_the_status_follows_the_faded_score(estimate, age_days, expected):
    r = row(estimate=estimate, stability=3.0, reviewed=T0)
    assert m.refreshed_fields(r, days(age_days)) == expected


def test_missed_stays_missed_however_the_score_fades():
    r = row(estimate=0.9, stability=3.0, reviewed=T0, status="missed")
    assert m.refreshed_fields(r, days(3)) == (45, "missed")
    assert m.refreshed_fields(r, days(0)) == (90, "missed")
