"""The arithmetic of the mastery model: an estimate of how well a topic is known, and a
memory strength that makes that estimate fade without review. Pure functions on any
object with the mastery fields; no database and no imports from app.models, so the
ORM can use it (models.py registers the hook that applies it when a row is loaded).

The model, in one paragraph. Each topic keeps `estimate` (0-1, how well it is known,
from evidence), `stability_days` (the half-life of the memory) and `last_reviewed_at`.
The score the student sees is `100 * estimate * retrievability`, where retrievability is
`0.5 ** (days since the last review / stability_days)`: it starts at 1 and halves every
`stability_days`. A graded quiz moves the estimate towards the fraction answered
correctly, weighted by how many questions there were (a long quiz is more evidence than
one lucky guess), and lengthens the stability when it went well, most of all when the
topic was already fading. A topic is "due for review" once retrievability drops below
DUE_RETRIEVABILITY.

A row with no `last_reviewed_at` has no review history (a topic nobody has been quizzed
on, or a row written before the model existed): it is left exactly as stored.

Every constant below is a default from spaced-repetition practice, not tuned to this
app; they are in one place so they can be adjusted after real use.
"""

import math
from datetime import datetime
from typing import Optional

# Half-life of a memory after its first review.
INITIAL_STABILITY_DAYS = 3.0
MIN_STABILITY_DAYS = 1.0
# A quiz of n questions carries weight n / (n + QUIZ_WEIGHT_K) against what was already
# known: 1 question = 25%, 3 = 50%, 10 = 77%.
QUIZ_WEIGHT_K = 3
# A quiz at or above this fraction correct counts as a pass: the memory gets stronger.
PASS_FRACTION = 0.6
# On a pass: stability *= 1 + GROWTH * fraction_correct * (1 - retrievability_before).
GROWTH = 1.5
# On a fail: stability *= FAIL_FACTOR (but never below MIN_STABILITY_DAYS).
FAIL_FACTOR = 0.6
# Below this retrievability a topic that was learned is due for review.
DUE_RETRIEVABILITY = 0.8


def is_tracked(mastery) -> bool:
    """Whether the row has a review history for the model to work from."""
    return getattr(mastery, "last_reviewed_at", None) is not None


def days_since_review(mastery, now: datetime) -> float:
    return max(0.0, (now - mastery.last_reviewed_at).total_seconds() / 86400.0)


def retrievability(mastery, now: datetime) -> float:
    """How much of the memory is left, 0-1: 1 at the moment of review, halving every
    `stability_days`. 1 for a row with no review history."""
    if not is_tracked(mastery):
        return 1.0
    stability = max(float(mastery.stability_days or INITIAL_STABILITY_DAYS), MIN_STABILITY_DAYS)
    return 0.5 ** (days_since_review(mastery, now) / stability)


def effective_score(mastery, now: datetime) -> int:
    """The score the student sees now: estimate x what is left of the memory, 0-100."""
    value = 100.0 * float(mastery.estimate or 0.0) * retrievability(mastery, now)
    return max(0, min(100, int(round(value))))


def is_due_for_review(mastery, now: datetime) -> bool:
    """Something was learned, and enough of it has faded that it is time to review."""
    return (
        is_tracked(mastery)
        and float(mastery.estimate or 0.0) > 0.0
        and retrievability(mastery, now) < DUE_RETRIEVABILITY
    )


def days_overdue(mastery, now: datetime) -> float:
    """How many days ago the topic became due (0 if it is not due yet)."""
    if not is_tracked(mastery):
        return 0.0
    stability = max(float(mastery.stability_days or INITIAL_STABILITY_DAYS), MIN_STABILITY_DAYS)
    due_after = stability * math.log2(1.0 / DUE_RETRIEVABILITY)
    return max(0.0, days_since_review(mastery, now) - due_after)


def quiz_weight(total_questions: int) -> float:
    return total_questions / (total_questions + QUIZ_WEIGHT_K)


def after_quiz(mastery, correct: int, total: int, now: datetime) -> tuple:
    """(new estimate, new stability_days) after a graded quiz of `total` questions with
    `correct` right. Does not change the row."""
    fraction = correct / total
    weight = quiz_weight(total)
    estimate = (1.0 - weight) * float(mastery.estimate or 0.0) + weight * fraction

    if not is_tracked(mastery):
        stability = INITIAL_STABILITY_DAYS  # the first review: nothing has faded yet
    else:
        stability = max(float(mastery.stability_days or INITIAL_STABILITY_DAYS), MIN_STABILITY_DAYS)
        if fraction >= PASS_FRACTION:
            stability *= 1.0 + GROWTH * fraction * (1.0 - retrievability(mastery, now))
        else:
            stability = max(MIN_STABILITY_DAYS, stability * FAIL_FACTOR)
    return min(1.0, max(0.0, estimate)), stability


def estimate_for_effective_score(mastery, target_score: int, now: datetime) -> float:
    """The estimate that makes the score shown now equal `target_score`, given how much
    of the memory is left. Capped at 1: a faded topic can't be pushed above what its
    remaining memory allows by editing the number alone."""
    remaining = retrievability(mastery, now)
    if remaining <= 0.0:
        return 1.0 if target_score > 0 else 0.0
    return min(1.0, max(0.0, target_score / 100.0 / remaining))


def refreshed_fields(mastery, now: Optional[datetime] = None) -> Optional[tuple]:
    """(score, status_value) a tracked row shows at `now`, or None for an untracked row.

    The status follows the faded score (mastered >= 80, in progress 1-79, unmastered 0),
    except that "missed" is set by hand and stays until a review raises the score."""
    if not is_tracked(mastery):
        return None
    now = now or datetime.utcnow()
    score = effective_score(mastery, now)
    status = getattr(mastery.status, "value", mastery.status)
    if status != "missed":
        status = "mastered" if score >= 80 else ("in_progress" if score > 0 else "unmastered")
    return score, status
