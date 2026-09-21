"""Pure text chunking — no I/O, no third-party imports.

A simple sliding window over characters, snapped to whitespace so
chunks don't split mid-word, with configurable overlap so a sentence
sitting on a chunk boundary still appears whole in at least one chunk.
Deliberately not tokenizer-aware (no tiktoken/model-specific tokenizer
dependency) — character count is a fine proxy for a small portfolio
project's chunk sizes, and keeps this module dependency-free and
trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkSpan:
    text: str
    char_start: int
    char_end: int


def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 150) -> list[ChunkSpan]:
    """Split ``text`` into overlapping :class:`ChunkSpan`s.

    ``char_start``/``char_end`` index into the original, unmodified
    ``text`` (not the stripped chunk), so a citation can point back at
    the exact source excerpt.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be non-negative")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    n = len(text)
    spans: list[ChunkSpan] = []
    start = 0

    while start < n:
        while start < n and text[start].isspace():
            start += 1
        if start >= n:
            break

        end = min(start + chunk_size, n)
        if end < n:
            snap = text.rfind(" ", start, end)
            if snap > start:
                end = snap

        if end <= start:
            end = min(start + chunk_size, n)

        spans.append(ChunkSpan(text=text[start:end], char_start=start, char_end=end))

        if end >= n:
            break

        next_start = end - chunk_overlap
        start = next_start if next_start > start else end

    return spans
