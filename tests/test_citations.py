"""Tests for citation extraction (app/generation/citations.py)."""

from app.generation.citations import extract_citation_indices, resolve_citations
from app.generation.comparison import TrialChunk


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


class TestExtractCitationIndices:
    def test_no_citations(self):
        assert extract_citation_indices("Plain text with no markers.") == []

    def test_single_citation(self):
        assert extract_citation_indices("Overall survival improved [1].") == [1]

    def test_multiple_separate_citations_in_order(self):
        assert extract_citation_indices("First claim [2]. Second claim [1].") == [2, 1]

    def test_comma_grouped_citation(self):
        assert extract_citation_indices("Effect was consistent [1, 3].") == [1, 3]

    def test_deduplicates_repeated_indices(self):
        assert extract_citation_indices("[1] and again [1] and [2].") == [1, 2]

    def test_adjacent_bracket_citations(self):
        assert extract_citation_indices("Supported by two sources[1][2].") == [1, 2]

    def test_ignores_non_numeric_brackets(self):
        assert extract_citation_indices("See the [Appendix] for details.") == []


class TestResolveCitations:
    def test_valid_index_resolves_to_the_right_chunk(self):
        chunks = [_chunk(1), _chunk(2), _chunk(3)]
        records = resolve_citations("Claim [2].", chunks)

        assert len(records) == 1
        assert records[0].index == 2
        assert records[0].is_valid
        assert records[0].chunk is chunks[1]

    def test_out_of_range_index_is_invalid(self):
        chunks = [_chunk(1)]
        records = resolve_citations("Claim [5].", chunks)

        assert len(records) == 1
        assert records[0].index == 5
        assert not records[0].is_valid
        assert records[0].chunk is None

    def test_zero_index_is_invalid(self):
        chunks = [_chunk(1)]
        records = resolve_citations("Claim [0].", chunks)

        assert not records[0].is_valid

    def test_empty_chunk_list_makes_every_citation_invalid(self):
        records = resolve_citations("Claim [1].", [])
        assert records[0].chunk is None

    def test_multiple_citations_resolve_independently(self):
        chunks = [_chunk(1), _chunk(2)]
        records = resolve_citations("Claim [1, 9].", chunks)

        by_index = {r.index: r for r in records}
        assert by_index[1].is_valid
        assert not by_index[9].is_valid
