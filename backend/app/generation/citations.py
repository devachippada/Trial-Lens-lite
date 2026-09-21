"""Citation extraction — pure, no I/O.

Claude is instructed (see ``app/generation/prompt.py``) to cite evidence
with bracketed indices like ``[1]`` or ``[1, 3]`` that refer to the
1-based position of a ``<retrieved_chunk>`` block in the prompt it was
sent. This module turns those markers back into structured citations
against the actual list of chunks that were retrieved for this request
— it never trusts the answer text for anything beyond "which index was
written here"; whether that index is real is decided purely by whether
it falls within the retrieved list, in ``resolve_citations`` below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.generation.types import EvidenceChunk

# Matches one bracketed citation group, e.g. "[1]" or "[1, 3]" — content
# is one or more integers separated by commas.
_CITATION_GROUP_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


@dataclass(frozen=True)
class CitationRecord:
    index: int
    # None when `index` didn't correspond to any chunk actually
    # retrieved for this request — a fabricated or stale citation.
    chunk: EvidenceChunk | None

    @property
    def is_valid(self) -> bool:
        return self.chunk is not None


def extract_citation_indices(text: str) -> list[int]:
    """Every citation index referenced in ``text``, first-appearance order, deduplicated."""

    seen: dict[int, None] = {}
    for group in _CITATION_GROUP_PATTERN.findall(text):
        for piece in group.split(","):
            seen.setdefault(int(piece.strip()), None)
    return list(seen.keys())


def resolve_citations(text: str, chunks: Sequence[EvidenceChunk]) -> list[CitationRecord]:
    """Map every citation index in ``text`` to the chunk at that 1-based
    position in ``chunks``, or to ``None`` if the index is out of range.

    ``chunks`` must be the exact same list, in the exact same order,
    that was passed to ``build_user_prompt``/``build_comparison_user_prompt``
    — the numbering is entirely positional, not a lookup by chunk_id.
    """

    records = []
    for index in extract_citation_indices(text):
        chunk = chunks[index - 1] if 1 <= index <= len(chunks) else None
        records.append(CitationRecord(index=index, chunk=chunk))
    return records
