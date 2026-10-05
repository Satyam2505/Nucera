"""Position bookkeeping for ordered children (modules in a course, topics
in a module).

Positions are 0-based and kept contiguous. There is deliberately no unique
constraint on (parent, position): a reorder rewrites every sibling inside
one transaction, and a unique constraint would make intermediate swap
states conflict. Callers commit.
"""

from typing import List, Sequence, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def repack(siblings: Sequence[T]) -> None:
    """Renumber `siblings` (already in the desired order) from 0."""
    for index, item in enumerate(siblings):
        item.position = index


def next_position(siblings: Sequence[T]) -> int:
    return len(siblings)


def apply_order(siblings: Sequence[T], ordered_ids: List[int]) -> None:
    """Reorder to match `ordered_ids`, which must be exactly the current set
    of sibling ids (no missing, extra or duplicate ids)."""
    by_id = {item.id: item for item in siblings}
    if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != set(by_id):
        raise HTTPException(
            status_code=400,
            detail="ids must list every existing item exactly once",
        )
    repack([by_id[item_id] for item_id in ordered_ids])


def move_to_index(siblings: Sequence[T], item: T, index: int) -> None:
    """Move `item` to `index` (clamped) among `siblings`, then repack."""
    ordered = [s for s in siblings if s is not item]
    index = max(0, min(index, len(ordered)))
    ordered.insert(index, item)
    repack(ordered)
