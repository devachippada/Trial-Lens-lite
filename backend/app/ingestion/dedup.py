"""Pure duplicate-detection logic: source-ID + content-hash based.

Two independent checks, both required by the Phase 2 spec:

1. **Source-ID dedup** — a record is identified first by its natural key
   (``nct_id`` / ``pmid``). ``classify_by_source_id`` decides whether an
   incoming record is new, an unchanged re-fetch, or an update to a
   record we already have, purely from hash comparison (no DB access,
   so it's trivially unit-testable).
2. **Content-hash collision detection** — separately, ``find_hash_collisions``
   flags when two *different* source IDs produced identical content
   (e.g. a withdrawn/duplicate PubMed record republished under a new
   PMID). This never blocks ingestion; it's a signal to log and review,
   since silently merging two distinct source identifiers would violate
   "preserve study identifiers ... exactly as published".

Nothing here touches the database or network — callers (the ingestion
scripts) do the lookup and pass in plain hashes/ids.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum


class DedupAction(str, Enum):
    NEW = "new"
    UNCHANGED = "unchanged"
    UPDATED = "updated"


@dataclass(frozen=True)
class DedupResult:
    action: DedupAction
    existing_id: int | None = None


def classify_by_source_id(
    existing_id: int | None, existing_content_hash: str | None, new_content_hash: str
) -> DedupResult:
    """Decide what to do with an incoming record already looked up by its
    natural key (``nct_id``/``pmid``).

    - No existing row (``existing_id is None``) -> NEW.
    - Existing row with the same content hash -> UNCHANGED (skip write).
    - Existing row with a different content hash -> UPDATED (upstream
      changed since we last ingested it).
    """

    if existing_id is None:
        return DedupResult(DedupAction.NEW)
    if existing_content_hash == new_content_hash:
        return DedupResult(DedupAction.UNCHANGED, existing_id=existing_id)
    return DedupResult(DedupAction.UPDATED, existing_id=existing_id)


def find_hash_collisions(hash_by_source_id: dict[str, str]) -> dict[str, list[str]]:
    """Given ``{source_id: content_hash}``, return groups of source IDs
    that share an identical content hash (only groups with 2+ members).

    Used both within a single ingestion batch and against the full table
    (pass in existing DB rows too) to catch cross-record duplicates that
    source-ID dedup alone can't see.
    """

    source_ids_by_hash: dict[str, list[str]] = defaultdict(list)
    for source_id, content_hash in hash_by_source_id.items():
        source_ids_by_hash[content_hash].append(source_id)

    return {
        content_hash: sorted(source_ids)
        for content_hash, source_ids in source_ids_by_hash.items()
        if len(source_ids) > 1
    }
