"""The one place that decides a topic's mastery status from its score.

The rule:
- score >= 80        -> mastered
- 0 < score < 80     -> in_progress
- score == 0         -> unmastered
- "missed" is the exception to being derived: it is set explicitly (POST
  /mastery/{id}/missed) and is cleared by the next change that actually
  raises the score. A change that does not raise it (a zero or negative
  delta, a delta at the 100 cap, a PUT to a lower or equal score) leaves a
  missed topic missed.

Scores are always clamped to 0..100. Everything that changes a score (quiz
grading, POST /sessions, PUT /mastery) goes through apply_score_delta or
set_score, so the status can never disagree with the score.
"""

from app import models

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


def apply_score_delta(mastery: models.Mastery, score_delta: int) -> None:
    """Add `score_delta` to the score (clamped) and re-derive the status."""
    set_score(mastery, mastery.score + score_delta)
