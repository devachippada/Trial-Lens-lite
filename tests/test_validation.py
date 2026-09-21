"""Tests for grounding validation (app/generation/validation.py).

Covers the two explicit Phase 4 test requirements this module exists
for: detecting an "invalid citation" (an index that doesn't correspond
to any retrieved chunk) and detecting an "unsupported claim" (a
substantive sentence with no citation at all).
"""

from app.generation.comparison import TrialChunk
from app.generation.validation import (
    MIN_CITABLE_SENTENCE_LENGTH,
    find_uncited_sentences,
    split_into_sentences,
    validate_answer,
)


def _chunk(chunk_id):
    return TrialChunk(
        chunk_id=chunk_id,
        document_id=chunk_id,
        source_type="trial",
        source_identifier=f"NCT0000000{chunk_id}",
        source_url="https://example.org",
        title="t",
        excerpt="e",
    )


class TestSplitIntoSentences:
    def test_splits_on_sentence_terminators(self):
        text = "First sentence. Second sentence! Third sentence?"
        assert split_into_sentences(text) == [
            "First sentence.",
            "Second sentence!",
            "Third sentence?",
        ]

    def test_single_sentence_with_no_terminator(self):
        assert split_into_sentences("just one clause with no period") == [
            "just one clause with no period"
        ]

    def test_empty_text_produces_no_sentences(self):
        assert split_into_sentences("") == []
        assert split_into_sentences("   ") == []


class TestFindUncitedSentences:
    def test_fully_cited_answer_has_no_uncited_sentences(self):
        text = (
            "Overall survival improved significantly in the treatment arm [1]. "
            "Adverse events were comparable between arms [2]."
        )
        assert find_uncited_sentences(text) == []

    def test_a_substantive_sentence_with_no_citation_is_flagged(self):
        text = (
            "Overall survival improved significantly in the treatment arm [1]. "
            "The drug is completely safe for everyone to use."
        )
        uncited = find_uncited_sentences(text)
        assert len(uncited) == 1
        assert "completely safe" in uncited[0]

    def test_short_sentences_are_exempt_from_the_citation_requirement(self):
        short = "Yes."
        assert len(short) < MIN_CITABLE_SENTENCE_LENGTH
        assert find_uncited_sentences(short) == []

    def test_every_sentence_uncited_when_answer_has_no_citations_at_all(self):
        text = (
            "The trial enrolled two hundred patients across several countries. "
            "Median follow-up was eighteen months in total."
        )
        assert len(find_uncited_sentences(text)) == 2


class TestValidateAnswer:
    def test_well_grounded_answer_is_valid(self):
        chunks = [_chunk(1), _chunk(2)]
        text = (
            "Overall survival improved in the treatment arm [1]. "
            "Adverse events were mild and self-limiting [2]."
        )

        result = validate_answer(text, chunks)

        assert result.is_valid
        assert result.invalid_citations == []
        assert result.uncited_sentences == []

    def test_citation_to_a_nonexistent_chunk_makes_the_answer_invalid(self):
        chunks = [_chunk(1)]
        text = (
            "Overall survival improved substantially in the treatment group [1]. "
            "The trial also showed a dramatic safety benefit [7]."
        )

        result = validate_answer(text, chunks)

        assert not result.is_valid
        assert len(result.invalid_citations) == 1
        assert result.invalid_citations[0].index == 7

    def test_uncited_substantive_claim_makes_the_answer_invalid(self):
        chunks = [_chunk(1)]
        text = (
            "Overall survival improved in the treatment arm [1]. "
            "This drug has no side effects whatsoever for any patient."
        )

        result = validate_answer(text, chunks)

        assert not result.is_valid
        assert result.invalid_citations == []
        assert len(result.uncited_sentences) == 1

    def test_both_problems_can_be_flagged_at_once(self):
        chunks = [_chunk(1)]
        text = (
            "This claim cites a chunk that was never retrieved [9]. "
            "This other claim cites nothing whatsoever here."
        )

        result = validate_answer(text, chunks)

        assert not result.is_valid
        assert len(result.invalid_citations) == 1
        assert len(result.uncited_sentences) == 1
