"""Tests for trial comparison (app/generation/comparison.py).

`assemble_trial_chunks` needs a real database (SQLAlchemy Trial/
Document/Chunk rows) and isn't exercised here — see
tests/test_comparison_db.py for that integration test, and
docs/phase-4-notes.md for why this sandbox can't run it. Everything
else — prompt building and the full generate/validate pipeline — is
pure and runs with plain `TrialChunk` fixtures, no DB needed.
"""

from app.generation.client import ClaudeResponse
from app.generation.comparison import (
    TrialChunk,
    build_comparison_user_prompt,
    generate_comparison,
)
from app.generation.prompt import ABSTAIN_MARKER


def _chunk(chunk_id, excerpt):
    return TrialChunk(
        chunk_id=chunk_id,
        document_id=chunk_id,
        source_type="trial",
        source_identifier=f"NCT0000000{chunk_id}",
        source_url="https://example.org",
        title="t",
        excerpt=excerpt,
    )


class _FakeClaudeClient:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def complete(self, *, system, user, max_tokens):
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        return ClaudeResponse(text=self.text)


class TestBuildComparisonUserPrompt:
    def test_numbers_chunks_continuously_across_both_trials(self):
        chunks_a = [_chunk(1, "Trial A enrolled 200 patients.")]
        chunks_b = [
            _chunk(2, "Trial B enrolled 150 patients."),
            _chunk(3, "Trial B used a different endpoint."),
        ]

        prompt, all_chunks = build_comparison_user_prompt("NCT001", chunks_a, "NCT002", chunks_b)

        assert [c.chunk_id for c in all_chunks] == [1, 2, 3]
        assert 'index="1"' in prompt
        assert 'index="2"' in prompt
        assert 'index="3"' in prompt
        assert prompt.index("Trial A enrolled 200 patients.") < prompt.index(
            "Trial B enrolled 150 patients."
        )

    def test_labels_each_section_with_its_nct_id(self):
        prompt, _ = build_comparison_user_prompt(
            "NCT00000001", [_chunk(1, "x")], "NCT00000002", [_chunk(2, "y")]
        )

        assert "Trial A (NCT00000001)" in prompt
        assert "Trial B (NCT00000002)" in prompt

    def test_missing_evidence_for_one_trial_is_noted_rather_than_left_blank(self):
        prompt, _ = build_comparison_user_prompt("NCT001", [], "NCT002", [_chunk(2, "y")])

        assert "no evidence retrieved for this trial" in prompt


class TestGenerateComparison:
    def test_well_grounded_comparison_is_returned(self):
        chunks_a = [_chunk(1, "Trial A enrolled 200 patients.")]
        chunks_b = [_chunk(2, "Trial B enrolled 150 patients.")]
        client = _FakeClaudeClient("Trial A enrolled 200 patients [1], while Trial B enrolled 150 [2].")

        result = generate_comparison("NCT001", chunks_a, "NCT002", chunks_b, client)

        assert result.status == "answered"
        assert len(result.citations) == 2

    def test_no_evidence_for_either_trial_short_circuits_without_calling_claude(self):
        client = _FakeClaudeClient("should never be used")

        result = generate_comparison("NCT001", [], "NCT002", [], client)

        assert result.status == "insufficient_evidence"
        assert client.calls == []

    def test_model_abstention_is_respected(self):
        chunks_a = [_chunk(1, "some text")]
        client = _FakeClaudeClient(ABSTAIN_MARKER)

        result = generate_comparison("NCT001", chunks_a, "NCT002", [], client)

        assert result.status == "insufficient_evidence"

    def test_citation_into_either_trials_range_validates_correctly(self):
        # Index 2 belongs to Trial B's chunk in the combined numbering —
        # citing it from a claim about Trial B is valid; the validator
        # doesn't care which "half" a citation lands in, only whether
        # the combined index is real.
        chunks_a = [_chunk(1, "Trial A used a single-arm design.")]
        chunks_b = [_chunk(2, "Trial B used a randomized design.")]
        client = _FakeClaudeClient(
            "Trial B used a randomized design [2], unlike Trial A's single-arm design [1]."
        )

        result = generate_comparison("NCT001", chunks_a, "NCT002", chunks_b, client)

        assert result.status == "answered"
        cited_ids = {c.chunk.chunk_id for c in result.citations}
        assert cited_ids == {1, 2}

    def test_fabricated_citation_fails_validation(self):
        chunks_a = [_chunk(1, "Trial A data.")]
        chunks_b = [_chunk(2, "Trial B data.")]
        client = _FakeClaudeClient("Trial A showed a dramatic benefit not seen elsewhere [50].")

        result = generate_comparison("NCT001", chunks_a, "NCT002", chunks_b, client)

        assert result.status == "validation_failed"
        assert result.citations == []
