"""CLI: (re-)chunk and embed every Document into Chunk rows.

Usage:

    python -m app.retrieval.index_documents --verbose

Safe to re-run: chunks are matched by (document_id, chunk_index) and
compared by content hash, so unchanged text is skipped, changed text is
re-embedded in place, and chunks left over from a document that got
shorter are removed.
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.ingestion.normalize import sha256_hex
from app.models import Chunk, Document
from app.retrieval.chunking import chunk_text
from app.retrieval.config import DEFAULTS
from app.retrieval.embeddings import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)


def index_document(session: Session, document: Document, provider: EmbeddingProvider) -> dict[str, int]:
    counts = {"created": 0, "updated": 0, "unchanged": 0, "deleted": 0}

    spans = chunk_text(document.text, chunk_size=DEFAULTS.chunk_size, chunk_overlap=DEFAULTS.chunk_overlap)
    existing_by_index = {
        c.chunk_index: c for c in session.query(Chunk).filter_by(document_id=document.id)
    }

    if not spans:
        for stale in existing_by_index.values():
            session.delete(stale)
            counts["deleted"] += 1
        return counts

    # Only embed spans whose text actually changed (or are new) — no point
    # re-calling the embedding provider for unchanged chunks.
    to_embed_indices: list[int] = []
    to_embed_texts: list[str] = []
    content_hashes = [sha256_hex(span.text) for span in spans]

    for idx, (span, content_hash) in enumerate(zip(spans, content_hashes)):
        existing = existing_by_index.get(idx)
        if existing is None or existing.content_hash != content_hash:
            to_embed_indices.append(idx)
            to_embed_texts.append(span.text)

    embeddings_by_index: dict[int, list[float]] = {}
    if to_embed_texts:
        vectors = provider.embed(to_embed_texts)
        embeddings_by_index = dict(zip(to_embed_indices, vectors))

    for idx, (span, content_hash) in enumerate(zip(spans, content_hashes)):
        existing = existing_by_index.get(idx)
        if existing is None:
            session.add(
                Chunk(
                    document_id=document.id,
                    chunk_index=idx,
                    text=span.text,
                    char_start=span.char_start,
                    char_end=span.char_end,
                    content_hash=content_hash,
                    embedding=embeddings_by_index[idx],
                )
            )
            counts["created"] += 1
        elif existing.content_hash != content_hash:
            existing.text = span.text
            existing.char_start = span.char_start
            existing.char_end = span.char_end
            existing.content_hash = content_hash
            existing.embedding = embeddings_by_index[idx]
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    for idx, stale in existing_by_index.items():
        if idx >= len(spans):
            session.delete(stale)
            counts["deleted"] += 1

    return counts


def run() -> dict[str, int]:
    settings = get_settings()
    provider = get_embedding_provider(settings)
    totals = {"documents": 0, "created": 0, "updated": 0, "unchanged": 0, "deleted": 0}

    with SessionLocal() as session:
        documents = session.query(Document).all()
        for document in documents:
            counts = index_document(session, document, provider)
            totals["documents"] += 1
            for key in ("created", "updated", "unchanged", "deleted"):
                totals[key] += counts[key]
            logger.info("document %s: %s", document.source_identifier, counts)
        session.commit()

    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    totals = run()
    print(
        f"Indexing complete: {totals['documents']} documents, "
        f"{totals['created']} chunks created, {totals['updated']} updated, "
        f"{totals['unchanged']} unchanged, {totals['deleted']} deleted"
    )


if __name__ == "__main__":
    main()
