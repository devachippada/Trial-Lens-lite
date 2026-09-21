"""Shared small data shapes for the retrieval package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoredChunk:
    """One chunk_id ranked by a single retriever, best-first."""

    chunk_id: int
    score: float
