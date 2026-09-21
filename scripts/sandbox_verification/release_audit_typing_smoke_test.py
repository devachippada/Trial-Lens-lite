"""Audit smoke test: exercises the exact functions touched by the
release-hardening audit's typing fixes (app/generation/types.py's
EvidenceChunk Protocol, app/generation/answer.py, comparison.py,
citations.py, validation.py, prompt.py, app/retrieval/fusion.py) plus
app/api/qa.py's _to_citation_out/_to_answer_out refactor, all of which
are pure/dependency-free by design. Confirms the type-annotation-only
edits made during this audit did not change runtime behavior.

Run directly with `python3 audit_smoke_test.py` (no pytest, no DB, no
network, no third-party packages needed).
"""

import sys

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label}")


# --- app.retrieval.fusion: FusedResult now Generic[ItemId] -----------------
from app.retrieval.fusion import reciprocal_rank_fusion, FusedResult

fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "c", "d"]], k=60)
check("fusion returns FusedResult instances", all(isinstance(f, FusedResult) for f in fused))
check("fusion ranks item in both lists highest", fused[0].item_id in ("b", "c"))
check("fusion score is positive", all(f.score > 0 for f in fused))
# item_id can be an int too (Generic in action)
fused_int = reciprocal_rank_fusion([[1, 2], [2, 3]], k=60)
check("fusion works with int ItemId", fused_int[0].item_id == 2)

# --- app.generation.types: EvidenceChunk protocol, now property-based ------
from app.generation.types import EvidenceChunk
from dataclasses import dataclass


@dataclass(frozen=True)
class FakeChunk:
    chunk_id: int
    document_id: int
    source_type: str
    source_identifier: str
    source_url: str
    title: str
    excerpt: str


c1 = FakeChunk(1, 1, "trial", "NCT001", "http://x", "Title A", "Excerpt about overall survival.")
c2 = FakeChunk(2, 2, "publication", "PMID001", "http://y", "Title B", "Excerpt about adverse events.")

check("frozen dataclass satisfies EvidenceChunk isinstance check", isinstance(c1, EvidenceChunk))

# --- app.generation.prompt: build_user_prompt (Sequence param) ------------
from app.generation.prompt import build_user_prompt, ABSTAIN_MARKER

prompt_text = build_user_prompt("What was the primary endpoint?", [c1, c2])
check("build_user_prompt includes both excerpts", "overall survival" in prompt_text and "adverse events" in prompt_text)
check("build_user_prompt works with a tuple (Sequence, not just list)", "overall survival" in build_user_prompt("q", (c1, c2)))

# --- app.generation.citations: resolve_citations (Sequence param) ---------
from app.generation.citations import extract_citation_indices, resolve_citations

text = "The primary endpoint was overall survival [1]. Adverse events were reported [2]."
indices = extract_citation_indices(text)
check("extract_citation_indices finds [1] and [2]", indices == [1, 2])

records = resolve_citations(text, [c1, c2])
check("resolve_citations resolves both citations", all(r.is_valid for r in records))
check("resolve_citations maps [1] to c1", records[0].chunk is c1)

records_tuple_input = resolve_citations(text, (c1, c2))
check("resolve_citations works with a tuple input (Sequence)", records_tuple_input[0].chunk is c1)

bad_text = "Fabricated claim with a bogus citation [99]."
bad_records = resolve_citations(bad_text, [c1, c2])
check("resolve_citations returns None chunk for out-of-range index", bad_records[0].chunk is None)
check("CitationRecord.is_valid is False for unresolved citation", bad_records[0].is_valid is False)

# --- app.generation.validation: validate_answer (Sequence param) ----------
from app.generation.validation import validate_answer

good_validation = validate_answer(text, [c1, c2])
check("validate_answer: fully grounded answer is_valid", good_validation.is_valid)

bad_validation = validate_answer(bad_text, [c1, c2])
check("validate_answer: fabricated citation makes is_valid False", not bad_validation.is_valid)
check("validate_answer: invalid_citations non-empty for fabricated citation", len(bad_validation.invalid_citations) == 1)

# --- app.generation.answer: generate_answer / finalize_response -----------
from app.generation.answer import generate_answer, finalize_response, AnswerResult
from app.generation.client import ClaudeResponse


class FakeClaudeClient:
    def __init__(self, text):
        self._text = text

    def complete(self, *, system, user, max_tokens):
        return ClaudeResponse(text=self._text)


result = generate_answer(
    query="What was the primary endpoint?",
    retrieve=lambda: [c1, c2],
    claude_client=FakeClaudeClient(text),
)
check("generate_answer: status answered for grounded response", result.status == "answered")
check("generate_answer: citations non-empty and all valid", len(result.citations) == 2 and all(c.is_valid for c in result.citations))

result_fabricated = generate_answer(
    query="q",
    retrieve=lambda: [c1, c2],
    claude_client=FakeClaudeClient(bad_text),
)
check("generate_answer: fabricated citation -> validation_failed", result_fabricated.status == "validation_failed")
check("generate_answer: validation_failed has NO citations shown", result_fabricated.citations == [])

result_abstain = generate_answer(
    query="q",
    retrieve=lambda: [c1, c2],
    claude_client=FakeClaudeClient(ABSTAIN_MARKER),
)
check("generate_answer: abstain marker -> insufficient_evidence", result_abstain.status == "insufficient_evidence")

result_no_chunks = generate_answer(
    query="q",
    retrieve=lambda: [],
    claude_client=FakeClaudeClient(text),
)
check("generate_answer: no chunks retrieved -> insufficient_evidence", result_no_chunks.status == "insufficient_evidence")

# --- app.generation.comparison: generate_comparison + TrialChunk ----------
from app.generation.comparison import generate_comparison, TrialChunk, build_comparison_user_prompt

t1 = TrialChunk(1, 1, "trial", "NCT001", "http://x", "Trial A design", "Randomized double-blind design [n=200].")
t2 = TrialChunk(2, 2, "trial", "NCT002", "http://y", "Trial B design", "Open-label single-arm design [n=100].")

check("TrialChunk satisfies EvidenceChunk isinstance check", isinstance(t1, EvidenceChunk))

cmp_prompt, all_chunks = build_comparison_user_prompt("NCT001", [t1], "NCT002", [t2])
check("build_comparison_user_prompt concatenates both trials' chunks", all_chunks == [t1, t2])
check("build_comparison_user_prompt works with tuples too", build_comparison_user_prompt("NCT001", (t1,), "NCT002", (t2,))[1] == [t1, t2])

cmp_text = "Trial A used a randomized double-blind design [1]. Trial B used an open-label design [2]."
cmp_result = generate_comparison("NCT001", [t1], "NCT002", [t2], FakeClaudeClient(cmp_text))
check("generate_comparison: grounded comparison -> answered", cmp_result.status == "answered")
check("generate_comparison: citations split across both trials", {c.chunk.source_identifier for c in cmp_result.citations} == {"NCT001", "NCT002"})

cmp_result_no_evidence = generate_comparison("NCT001", [], "NCT002", [], FakeClaudeClient(cmp_text))
check("generate_comparison: no evidence for either trial -> insufficient_evidence", cmp_result_no_evidence.status == "insufficient_evidence")

# with an explicit custom question (exercises app/api/qa.py's replaced-kwargs branch logic path indirectly)
cmp_result_custom_q = generate_comparison(
    "NCT001", [t1], "NCT002", [t2], FakeClaudeClient(cmp_text), question="Compare adverse event rates."
)
check("generate_comparison: custom question path still answers", cmp_result_custom_q.status == "answered")

# --- app.api.qa._to_answer_out / _to_citation_out ---------------------
# app/api/qa.py imports fastapi + sqlalchemy at module level, neither of
# which is installed in this sandbox (same constraint as every prior
# phase), so it can't be imported directly here. Instead, reproduce its
# exact logic inline (copied verbatim from the current source) against
# the same fake AnswerResult objects, to confirm the refactored
# _to_citation_out/_to_answer_out behave correctly against real
# CitationRecord/AnswerResult instances.
from app.generation.citations import CitationRecord


def _to_citation_out_reproduction(citation: CitationRecord):
    chunk = citation.chunk
    assert chunk is not None, "AnswerResult.citations must only contain resolved citations"
    return {
        "index": citation.index,
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "source_type": chunk.source_type,
        "source_identifier": chunk.source_identifier,
        "source_url": chunk.source_url,
        "title": chunk.title,
        "excerpt": chunk.excerpt,
    }


def _to_answer_out_reproduction(result: AnswerResult):
    return {
        "status": result.status,
        "query": result.query,
        "answer": result.answer,
        "citations": [_to_citation_out_reproduction(c) for c in result.citations],
        "warnings": result.warnings,
    }


answer_out = _to_answer_out_reproduction(result)
check("_to_answer_out: status carried through", answer_out["status"] == "answered")
check("_to_answer_out: citation chunk fields populated correctly", answer_out["citations"][0]["source_identifier"] in ("NCT001", "PMID001"))
check("_to_answer_out: excerpt text carried through", answer_out["citations"][0]["excerpt"] in (c1.excerpt, c2.excerpt))

# _to_citation_out's assert should fire loudly if ever given an invalid (None-chunk) citation
try:
    _to_citation_out_reproduction(bad_records[0])
    check("_to_citation_out: should have raised AssertionError on unresolved citation", False)
except AssertionError:
    check("_to_citation_out: correctly asserts on unresolved citation (defense in depth)", True)

cmp_answer_out = _to_answer_out_reproduction(cmp_result)
check("_to_answer_out works for comparison results too", len(cmp_answer_out["citations"]) == 2)

print()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
