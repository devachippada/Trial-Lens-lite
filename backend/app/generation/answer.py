"""Grounded answer generation orchestration.

Deliberately decoupled from retrieval and from the Claude SDK by taking
both as parameters: ``retrieve`` is a zero-argument callable that
returns whatever evidence the caller wants (in production, a closure
over ``app.retrieval.hybrid.search`` against a live DB and embedding
provider — see ``app/api/qa.py``; in tests, a fake returning a fixed
list), and ``claude_client`` satisfies the tiny ``ClaudeClient``
protocol (in production, ``AnthropicClaudeClient``; in tests, a fake
returning a scripted response).

That split is what makes this module's four responsibilities —
grounded generation, insufficient-evidence abstention, citation
extraction, and citation validation — directly testable without a
database, an API key, or network access, and it does so without
changing anything in ``app/retrieval/``: ``hybrid.search`` is called
exactly as Phase 3 left it, just wrapped in a closure at the call site.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Sequence

from app.generation.citations import CitationRecord
from app.generation.client import ClaudeClient
from app.generation.config import DEFAULTS
from app.generation.prompt import ABSTAIN_MARKER, build_system_prompt, build_user_prompt
from app.generation.types import EvidenceChunk
from app.generation.validation import validate_answer

AnswerStatus = Literal["answered", "insufficient_evidence", "validation_failed"]

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "There isn't enough retrieved evidence to answer this question. Try rephrasing "
    "it, or ask about a specific trial or publication that has been ingested."
)

VALIDATION_FAILED_MESSAGE = (
    "The generated answer didn't pass citation validation, so it isn't shown — "
    "this protects against unsupported or fabricated claims. Try rephrasing the "
    "question."
)


@dataclass(frozen=True)
class AnswerResult:
    status: AnswerStatus
    query: str
    answer: str | None
    citations: list[CitationRecord]
    warnings: list[str]


def _validation_warnings(validation) -> list[str]:
    warnings = []
    if validation.invalid_citations:
        indices = ", ".join(f"[{c.index}]" for c in validation.invalid_citations)
        warnings.append(f"answer cited {indices}, which do not correspond to any retrieved chunk")
    if validation.uncited_sentences:
        warnings.append(
            f"{len(validation.uncited_sentences)} sentence(s) made a claim without citing evidence"
        )
    return warnings


def finalize_response(
    query: str,
    text: str,
    chunks: Sequence[EvidenceChunk],
    *,
    validation_failed_message: str = VALIDATION_FAILED_MESSAGE,
) -> AnswerResult:
    """Turn raw model output into an ``AnswerResult``: abstain-check, then
    validate citations/grounding against ``chunks``. Shared by
    ``generate_answer`` and ``app.generation.comparison.generate_comparison``
    so both endpoints apply identical safety checks.
    """

    if text == ABSTAIN_MARKER:
        return AnswerResult(
            status="insufficient_evidence",
            query=query,
            answer=INSUFFICIENT_EVIDENCE_MESSAGE,
            citations=[],
            warnings=["model reported insufficient evidence"],
        )

    validation = validate_answer(text, chunks)
    if not validation.is_valid:
        return AnswerResult(
            status="validation_failed",
            query=query,
            answer=validation_failed_message,
            citations=[],
            warnings=_validation_warnings(validation),
        )

    return AnswerResult(
        status="answered",
        query=query,
        answer=text,
        citations=[c for c in validation.citations if c.is_valid],
        warnings=[],
    )


def generate_answer(
    query: str,
    retrieve: Callable[[], Sequence[EvidenceChunk]],
    claude_client: ClaudeClient,
    max_tokens: int = DEFAULTS.max_tokens,
) -> AnswerResult:
    chunks = retrieve()

    if not chunks:
        return AnswerResult(
            status="insufficient_evidence",
            query=query,
            answer=INSUFFICIENT_EVIDENCE_MESSAGE,
            citations=[],
            warnings=["no chunks retrieved for this query"],
        )

    system = build_system_prompt()
    user = build_user_prompt(query, chunks)
    response = claude_client.complete(system=system, user=user, max_tokens=max_tokens)

    return finalize_response(query, response.text.strip(), chunks)
