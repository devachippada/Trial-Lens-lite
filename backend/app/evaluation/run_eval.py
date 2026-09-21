"""CLI: run the Phase 6 evaluation end to end against a real database.

Usage:

    python -m app.evaluation.run_eval --claude-client real
    python -m app.evaluation.run_eval --claude-client fake-self-test --output /tmp/report.md

Requires a running Postgres reachable via ``DATABASE_URL`` with the
``vector`` extension installed (this sandbox's Postgres 16 install is
missing that extension's control file — see docs/phase-3-notes.md and
docs/phase-6-notes.md for why hybrid/dense retrieval can't run here),
the full backend dependency set (``sqlalchemy``, ``pgvector``, and for
``--claude-client real``, ``anthropic``), and — for
``--claude-client real`` (the default) — a real ``ANTHROPIC_API_KEY``,
since grading citation correctness/completeness/abstention accuracy
needs a real model response. There is deliberately no dependency-free
fake answer-generation provider for real use (see
``app/generation/client.py``'s docstring) — the one defined below exists
only to self-test this harness's own plumbing.

``--claude-client fake-self-test`` swaps in ``ScriptedFakeClaudeClient``
instead of a real model call. That mode exists ONLY to verify this
harness end to end (dataset loading, seeding, retrieval wiring, metric
computation, report rendering) without network access or an API key —
its citation-correctness/completeness/abstention-accuracy numbers must
never be read as real model performance. See docs/evaluation-report.md.

This script commits the seeded fixtures and indexed chunks rather than
rolling them back, so the corpus is inspectable afterward (re-running it
is safe: seeding is upsert-based, same as real ingestion).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
from typing import Callable, Sequence

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.evaluation.dataset import DEFAULT_QUESTIONS_PATH, load_questions, validate_questions
from app.evaluation.report import EvaluationReport, build_question_result, render_markdown
from app.evaluation.seed_fixtures import seed_all
from app.generation.answer import generate_answer
from app.generation.client import ClaudeClient, ClaudeResponse, get_claude_client
from app.generation.config import DEFAULTS as GENERATION_DEFAULTS
from app.generation.prompt import ABSTAIN_MARKER
from app.generation.types import EvidenceChunk
from app.models import Document
from app.retrieval.embeddings import get_embedding_provider
from app.retrieval.hybrid import RetrievalMode
from app.retrieval.hybrid import search as hybrid_search
from app.retrieval.index_documents import index_document

logger = logging.getLogger(__name__)

_CITATION_INDEX_PATTERN = re.compile(r'<retrieved_chunk index="(\d+)"')


class ScriptedFakeClaudeClient:
    """Deterministic stand-in for :class:`ClaudeClient` — self-test only,
    see this module's docstring.

    Cites every retrieved chunk in one generic sentence long enough to
    pass the citation-coverage check (so the harness's own plumbing —
    retrieval -> generation -> validation -> metrics — can be exercised
    without a real model call), or abstains if no evidence was given.
    It has no understanding of the question or the evidence, so its
    citation-correctness/completeness and abstention-accuracy scores
    reflect nothing about real answer quality; only Recall@5/MRR
    (computed from raw retrieval, before this client is ever called)
    are meaningful when this fake is used.
    """

    def complete(self, *, system: str, user: str, max_tokens: int) -> ClaudeResponse:
        indices = sorted({int(m) for m in _CITATION_INDEX_PATTERN.findall(user)})
        if not indices:
            return ClaudeResponse(text=ABSTAIN_MARKER)
        citation = ", ".join(str(i) for i in indices)
        return ClaudeResponse(
            text=f"This is a scripted self-test response citing the retrieved evidence [{citation}]."
        )


def _document_order(chunks) -> tuple[str, ...]:
    """Chunk-level results, deduplicated to document-level
    ``source_identifier``s, preserving first-seen (best-rank) order.
    """

    seen: list[str] = []
    seen_set: set[str] = set()
    for chunk in chunks:
        if chunk.source_identifier not in seen_set:
            seen_set.add(chunk.source_identifier)
            seen.append(chunk.source_identifier)
    return tuple(seen)


def _freeze(chunks: Sequence[EvidenceChunk]) -> Callable[[], Sequence[EvidenceChunk]]:
    """Capture ``chunks`` by value into a zero-arg callable.

    Equivalent to ``lambda: chunks`` but doesn't rely on a per-iteration
    default-argument trick to dodge Python's late-binding closure
    behavior (this is called fresh inside a ``for`` loop, once per
    question) — passing ``chunks`` as a real parameter here does the
    same job and is unambiguous to both readers and the type checker.
    """

    def _retrieve() -> Sequence[EvidenceChunk]:
        return chunks

    return _retrieve


def index_all_documents(session: Session, embedding_provider) -> int:
    """Chunk+embed every Document — same logic as
    ``app.retrieval.index_documents.run``, just scoped to one session
    the caller controls the transaction for.
    """

    documents = session.query(Document).all()
    total_chunks = 0
    for document in documents:
        counts = index_document(session, document, embedding_provider)
        total_chunks += counts["created"] + counts["updated"] + counts["unchanged"]
    return total_chunks


def run_evaluation(
    session: Session,
    claude_client: ClaudeClient,
    claude_client_kind: str,
    embedding_provider,
    embedding_provider_kind: str,
    retrieval_mode: RetrievalMode = "hybrid",
) -> EvaluationReport:
    questions = load_questions(DEFAULT_QUESTIONS_PATH)

    known_identifiers = {doc.source_identifier for doc in session.query(Document).all()}
    problems = validate_questions(questions, known_identifiers)
    if problems:
        raise ValueError("questions.json failed validation:\n" + "\n".join(problems))

    results = []
    for q in questions:
        chunks = hybrid_search(
            session,
            q.question,
            embedding_provider,
            mode=retrieval_mode,
            top_k=GENERATION_DEFAULTS.top_k_chunks,
        )
        retrieved = _document_order(chunks)

        answer_result = generate_answer(
            query=q.question,
            retrieve=_freeze(chunks),
            claude_client=claude_client,
        )
        cited_identifiers = []
        for c in answer_result.citations:
            # `finalize_response` only keeps citations with a resolved
            # chunk in `AnswerResult.citations` — see app/api/qa.py's
            # `_to_citation_out` for the same invariant, checked there too.
            assert c.chunk is not None, "AnswerResult.citations must only contain resolved citations"
            cited_identifiers.append(c.chunk.source_identifier)
        cited = tuple(dict.fromkeys(cited_identifiers))

        results.append(
            build_question_result(
                question_id=q.id,
                question=q.question,
                expect_answerable=q.expect_answerable,
                relevant_source_identifiers=q.relevant_source_identifiers,
                retrieved_source_identifiers=retrieved,
                actual_status=answer_result.status,
                cited_source_identifiers=cited,
            )
        )

    notes = []
    if claude_client_kind.startswith("scripted-fake"):
        notes.append(
            "Claude client is a scripted self-test fake: citation correctness/completeness "
            "and abstention accuracy above are a plumbing self-test, NOT real model performance. "
            "Only Recall@5/MRR are meaningful in this run."
        )
    if retrieval_mode != "hybrid":
        notes.append(f"Retrieval mode was '{retrieval_mode}', not the production default 'hybrid'.")

    return EvaluationReport(
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        claude_client_kind=claude_client_kind,
        embedding_provider_kind=embedding_provider_kind,
        retrieval_mode=retrieval_mode,
        question_results=results,
        notes=notes,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--claude-client",
        choices=["real", "fake-self-test"],
        default="real",
        help="'real' calls the configured Anthropic model (needs ANTHROPIC_API_KEY); "
        "'fake-self-test' uses a scripted stand-in to self-test the harness only.",
    )
    parser.add_argument("--output", default=None, help="Write the Markdown report to this path (also prints to stdout).")
    parser.add_argument("--mode", choices=["hybrid", "fulltext", "dense"], default="hybrid")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    settings = get_settings()
    embedding_provider = get_embedding_provider(settings)

    if args.claude_client == "real":
        claude_client = get_claude_client(settings)
        claude_client_kind = f"real ({settings.anthropic_model})"
    else:
        claude_client = ScriptedFakeClaudeClient()
        claude_client_kind = "scripted-fake (self-test only, not real model performance)"

    with SessionLocal() as session:
        seeded = seed_all(session)
        session.flush()
        chunks_indexed = index_all_documents(session, embedding_provider)
        session.commit()
        logger.info(
            "seeded %d trials, %d publications, indexed %d chunks",
            len(seeded["nct_ids"]),
            len(seeded["pmids"]),
            chunks_indexed,
        )

        report = run_evaluation(
            session,
            claude_client,
            claude_client_kind,
            embedding_provider,
            settings.embedding_provider,
            retrieval_mode=args.mode,
        )

    markdown = render_markdown(report)
    print(markdown)
    if args.output:
        with open(args.output, "w") as f:
            f.write(markdown)
        print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
