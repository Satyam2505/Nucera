"""The one place that decides a topic's mastery status from its score, and the one
place that changes a score.

The rule:
- score >= 80        -> mastered
- 0 < score < 80     -> in_progress
- score == 0         -> unmastered
- "missed" is the exception to being derived: it is set explicitly (POST
  /mastery/{id}/missed) and is cleared by the next change that actually
  raises the score. A change that does not raise it (a zero or negative
  delta, a delta at the 100 cap, a PUT to a lower or equal score) leaves a
  missed topic missed.

Scores are always clamped to 0..100. Everything that changes a score goes through this
module, so the status can never disagree with the score:

- record_quiz       a graded quiz: moves the estimate by how much evidence it is, and
                    restarts the topic's memory clock (services/mastery_model.py)
- override_score    a score typed in by hand (PUT /mastery): a fresh review at that level
- apply_score_delta a self-report (POST /sessions): changes the score by that much now,
                    without counting as a review, so the memory keeps fading from where
                    it was
- set_score         the raw rule above, used by the three

A topic with no review history (last_reviewed_at unset) keeps the old plain-integer
behaviour; it joins the memory model with its first quiz or manual score.
"""

from datetime import datetime
from typing import Optional

from app import models
from app.services import mastery_model

MASTERED_THRESHOLD = 80
MIN_SCORE = 0
MAX_SCORE = 100


def status_for_score(score: int) -> models.MasteryStatus:
    if score >= MASTERED_THRESHOLD:
        return models.MasteryStatus.mastered
    if score > 0:
        return models.MasteryStatus.in_progress
    return models.MasteryStatus.unmastered


def set_score(mastery: models.Mastery, score: int) -> None:
    """Set the (clamped) score and re-derive the status."""
    previous = mastery.score
    mastery.score = max(MIN_SCORE, min(MAX_SCORE, score))

    if mastery.status == models.MasteryStatus.missed and mastery.score <= previous:
        return
    mastery.status = status_for_score(mastery.score)


def apply_score_delta(
    mastery: models.Mastery, score_delta: int, now: Optional[datetime] = None
) -> None:
    """Change the score shown now by `score_delta` (clamped) and re-derive the status.

    On a topic with a review history this adjusts the estimate so the score shown right
    now moves by exactly that much; the review clock is untouched, so it keeps fading."""
    new_score = max(MIN_SCORE, min(MAX_SCORE, mastery.score + score_delta))
    if mastery_model.is_tracked(mastery):
        mastery.estimate = mastery_model.estimate_for_effective_score(
            mastery, new_score, now or datetime.utcnow()
        )
    set_score(mastery, new_score)


def override_score(mastery: models.Mastery, score: int, now: Optional[datetime] = None) -> None:
    """A score typed in by hand counts as a fresh review at that level: the estimate is
    the score, the memory clock restarts, and the half-life is kept (or the default)."""
    now = now or datetime.utcnow()
    score = max(MIN_SCORE, min(MAX_SCORE, score))
    set_score(mastery, score)
    mastery.estimate = score / 100.0
    mastery.last_reviewed_at = now
    mastery.stability_days = max(
        float(mastery.stability_days or 0.0), mastery_model.INITIAL_STABILITY_DAYS
    )


def record_quiz(
    mastery: models.Mastery, correct: int, total: int, now: Optional[datetime] = None
) -> int:
    """Fold a graded quiz (`correct` of `total` questions) into the topic. Returns the
    change in the score shown: the score after minus the score the student saw before."""
    now = now or datetime.utcnow()
    shown_before = mastery.score
    if not mastery_model.is_tracked(mastery) and not mastery.estimate:
        # No history yet: start from the stored score (rows written before the model).
        mastery.estimate = mastery.score / 100.0

    estimate, stability = mastery_model.after_quiz(mastery, correct, total, now)
    mastery.estimate = estimate
    mastery.stability_days = stability
    mastery.last_reviewed_at = now
    set_score(mastery, mastery_model.effective_score(mastery, now))
    return mastery.score - shown_before
