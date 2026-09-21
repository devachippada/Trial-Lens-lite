"""Reciprocal rank fusion — pure, no I/O.

RRF combines multiple ranked lists (e.g. one from full-text search, one
from dense/vector search) by rank position alone, not raw scores. That
sidesteps the problem of full-text ``ts_rank`` and cosine similarity
living on completely different, incomparable scales — RRF only needs to
know "how far down each list is this item", not what the scores mean.

Reference: Cormack, Clarke & Buettcher, "Reciprocal Rank Fusion
Outperforms Condorcet and Individual Rank Learning Methods" (SIGIR 2009).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Generic, Hashable, TypeVar

ItemId = TypeVar("ItemId", bound=Hashable)


@dataclass(frozen=True)
class FusedResult(Generic[ItemId]):
    item_id: ItemId
    score: float
    # Which input rankings (by index) this item appeared in — lets a
    # caller label a result "found by fulltext + dense" vs just one.
    source_ranks: dict[int, int]


def reciprocal_rank_fusion(
    rankings: list[list[ItemId]], k: int = 60
) -> list[FusedResult[ItemId]]:
    """Fuse multiple best-first ranked lists into one, by RRF score.

    ``rankings[i]`` is a best-first list of item IDs from retriever
    ``i`` (duplicates within one list are ignored beyond their first,
    best occurrence). Returns items sorted by descending fused score;
    an item that appears in more lists, or ranks higher within them,
    scores higher.
    """

    if k <= 0:
        raise ValueError("k must be positive")

    scores: dict[ItemId, float] = defaultdict(float)
    source_ranks: dict[ItemId, dict[int, int]] = defaultdict(dict)

    for source_index, ranking in enumerate(rankings):
        seen_in_this_list: set[ItemId] = set()
        for rank, item_id in enumerate(ranking, start=1):
            if item_id in seen_in_this_list:
                continue
            seen_in_this_list.add(item_id)
            scores[item_id] += 1.0 / (k + rank)
            source_ranks[item_id][source_index] = rank

    fused = [
        FusedResult(item_id=item_id, score=score, source_ranks=source_ranks[item_id])
        for item_id, score in scores.items()
    ]
    fused.sort(key=lambda r: r.score, reverse=True)
    return fused
