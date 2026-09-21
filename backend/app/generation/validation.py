"""Grounding validation for a generated answer — pure, no I/O.

Two independent, structural checks, both required for an answer to be
considered safe to show a user:

1. Every citation index the answer used must resolve to a chunk that
   was actually retrieved (``resolve_citations`` returns no ``None``
   chunk) — catches a fabricated or stale citation number, including
   one an attacker's injected chunk text tried to plant (see
   ``tests/test_prompt_injection.py``): validation only ever checks the
   index against the real retrieved-chunk list, never against anything
   written inside a chunk's own text.
2. Every substantive sentence must carry at least one citation marker —
   a crude but real defense against "unsupported claims": prose the
   model wrote without pointing at any evidence block at all.

This can't verify an answer is *true* — that would need an independent
evidence source this project doesn't have (a second model call, a human
reviewer, formal entailment checking). It verifies the narrower,
mechanically checkable claim: every assertion is at least *attributed*
to a source we can show the user, and every attribution points
somewhere real. That's deliberately a stricter, fail-closed policy —
see ``app/generation/answer.py``'s ``validation_failed`` status, which
never shows a partially-grounded answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.generation.citations import CitationRecord, resolve_citations
from app.generation.types import EvidenceChunk

# A "sentence" shorter than this (e.g. a heading, "Yes.", a transition
# like "In summary:") is exempt from the citation requirement — it's
# very unlikely to itself assert a checkable fact, and requiring
# citations on connective text would fail well-grounded answers for no
# real safety benefit. This is a heuristic threshold, not a claim that
# short sentences can never contain a fact.
MIN_CITABLE_SENTENCE_LENGTH = 25

_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_CITATION_PATTERN = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


def split_into_sentences(text: str) -> list[str]:
    """A deliberately simple sentence splitter (split after ``.``/``!``/``?``).

    Good enough for citation-coverage checking; not an NLP-grade
    tokenizer (it doesn't special-case abbreviations like "e.g." or
    decimal numbers) — see ``tests/test_validation.py`` for the exact
    behavior this implies and relies on.
    """

    return [s.strip() for s in _SENTENCE_SPLIT_PATTERN.split(text.strip()) if s.strip()]


def find_uncited_sentences(text: str) -> list[str]:
    """Substantive sentences with no ``[n]``-style citation marker anywhere in them."""

    return [
        sentence
        for sentence in split_into_sentences(text)
        if len(sentence) >= MIN_CITABLE_SENTENCE_LENGTH and not _CITATION_PATTERN.search(sentence)
    ]


@dataclass(frozen=True)
class ValidationResult:
    citations: list[CitationRecord]
    uncited_sentences: list[str]

    @property
    def invalid_citations(self) -> list[CitationRecord]:
        return [c for c in self.citations if not c.is_valid]

    @property
    def is_valid(self) -> bool:
        return not self.invalid_citations and not self.uncited_sentences


def validate_answer(text: str, chunks: Sequence[EvidenceChunk]) -> ValidationResult:
    return ValidationResult(
        citations=resolve_citations(text, chunks),
        uncited_sentences=find_uncited_sentences(text),
    )
