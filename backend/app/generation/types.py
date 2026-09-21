"""Shared structural type for a piece of retrieved evidence.

Deliberately a ``Protocol``, not an import of
``app.retrieval.hybrid.RetrievalResult``: that module imports
``app.models`` at load time (for the ORM join in ``_load_results``),
which pulls in SQLAlchemy and pgvector. Everything in
``app/generation/`` except the DB-touching edges (the real retrieval
call, the trial-chunk DB lookup) has no need for either — it only reads
these six fields — so depending on the *shape* rather than the concrete
class keeps prompt/citation/validation logic importable and directly
testable with zero third-party packages, exactly like
``app/retrieval/chunking.py`` and ``fusion.py`` were kept dependency-free
in Phase 3. ``RetrievalResult`` and the plain ``TrialChunk`` dataclass in
``app/generation/comparison.py`` both satisfy this structurally, with no
inheritance needed.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EvidenceChunk(Protocol):
    """Structurally, a *read-only* view over these seven fields.

    Declared with ``@property`` rather than plain attribute annotations
    so that frozen dataclasses (``app.retrieval.hybrid.RetrievalResult``,
    ``app.generation.comparison.TrialChunk``) satisfy this Protocol
    under mypy: a bare attribute annotation on a ``Protocol`` implies a
    *settable* member (see PEP 544), which a frozen dataclass's
    read-only field can never match, even though the two are
    functionally identical at runtime (attribute access either way).
    Using ``@property`` here asks only "can this be read", which is
    exactly what every caller in this module actually does.
    """

    @property
    def chunk_id(self) -> int: ...
    @property
    def document_id(self) -> int: ...
    @property
    def source_type(self) -> str: ...
    @property
    def source_identifier(self) -> str: ...
    @property
    def source_url(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def excerpt(self) -> str: ...
