"""Tests for grounded answer generation orchestration (app/generation/answer.py).

`retrieve` and `claude_client` are both fakes here — no database, no
API key, and no network access are needed to exercise the full
pipeline: retrieval -> prompt -> (simulated) Claude response ->
abstain-check -> citation validation -> final AnswerResult.
"""

from app.generation.answer import generate_answer
from app.generation.client import ClaudeResponse
from app.generation.comparison import TrialChunk
from app.generation.prompt import ABSTAIN_MARKER


def _chunk(chunk_id=1, excerpt="Overall survival improved in the treatment arm."):
    return TrialChunk(
        chunk_id=chunk_id,
        document_id=chunk_id,
        source_type="trial",
        source_identifier="NCT00000001",
        source_url="https://clinicaltrials.gov/study/NCT00000001",
        title="A test trial",
        excerpt=excerpt,
    )


class _FakeClaudeClient:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def complete(self, *, system, user, max_tokens):
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        return ClaudeResponse(text=self.text)


class TestGeneratedAnswerHappyPath:
    def test_well_grounded_answer_is_returned_with_valid_citations(self):
        chunks = [_chunk(chunk_id=1)]
        client = _FakeClaudeClient("Overall survival improved in the treatment arm [1].")

        result = generate_answer(
            "What happened to overall survival?", retrieve=lambda: chunks, claude_client=client
        )

        assert result.status == "answered"
        assert result.answer == "Overall survival improved in the treatment arm [1]."
        assert len(result.citations) == 1
        assert result.citations[0].chunk.chunk_id == 1
        assert result.warnings == []

    def test_the_actual_retrieved_chunks_are_what_gets_sent_to_claude(self):
        chunks = [_chunk(chunk_id=1, excerpt="A unique excerpt marker XYZ123.")]
        client = _FakeClaudeClient("It mentions XYZ123 [1].")

        generate_answer("q", retrieve=lambda: chunks, claude_client=client)

        [call] = client.calls
        assert "A unique excerpt marker XYZ123." in call["user"]


class TestInsufficientEvidence:
    def test_zero_retrieved_chunks_short_circuits_without_calling_claude(self):
        client = _FakeClaudeClient("should never be used")

        result = generate_answer("q", retrieve=lambda: [], claude_client=client)

        assert result.status == "insufficient_evidence"
        assert client.calls == []  # no API call was made at all

    def test_model_abstention_marker_is_treated_as_insufficient_evidence(self):
        chunks = [_chunk()]
        client = _FakeClaudeClient(ABSTAIN_MARKER)

        result = generate_answer("q", retrieve=lambda: chunks, claude_client=client)

        assert result.status == "insufficient_evidence"
        assert result.citations == []
        assert result.answer != ABSTAIN_MARKER  # the raw marker is never shown to a user


class TestValidationFailure:
    def test_citation_to_a_chunk_that_was_never_retrieved_fails_validation(self):
        chunks = [_chunk(chunk_id=1)]
        client = _FakeClaudeClient("Overall survival improved dramatically [4].")

        result = generate_answer("q", retrieve=lambda: chunks, claude_client=client)

        assert result.status == "validation_failed"
        assert result.citations == []  # never surface a fabricated citation
        assert any("[4]" in w for w in result.warnings)

    def test_uncited_claim_fails_validation(self):
        chunks = [_chunk(chunk_id=1)]
        client = _FakeClaudeClient("This medication has zero side effects for any patient in existence.")

        result = generate_answer("q", retrieve=lambda: chunks, claude_client=client)

        assert result.status == "validation_failed"
        assert result.citations == []

    def test_the_unsafe_answer_text_is_never_returned_to_the_caller(self):
        chunks = [_chunk(chunk_id=1)]
        fabricated = "The trial secretly proved the drug cures everything [99]."
        client = _FakeClaudeClient(fabricated)

        result = generate_answer("q", retrieve=lambda: chunks, claude_client=client)

        assert result.answer != fabricated
