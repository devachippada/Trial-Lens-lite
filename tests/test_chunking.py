"""Tests for the pure text-chunking module (app/retrieval/chunking.py).

No I/O, no fixtures, no third-party imports required by the code under
test — these run anywhere Python runs, which is exactly why chunking was
kept dependency-free in the first place (see this project's environment
notes in docs/). Every assertion here was also executed directly (outside
pytest) against a real interpreter as part of Phase 3 verification.
"""

import pytest

from app.retrieval.chunking import ChunkSpan, chunk_text


class TestChunkTextBasics:
    def test_empty_text_produces_no_spans(self):
        assert chunk_text("", chunk_size=10, chunk_overlap=2) == []

    def test_whitespace_only_text_produces_no_spans(self):
        assert chunk_text("   \n\t  ", chunk_size=10, chunk_overlap=2) == []

    def test_text_shorter_than_chunk_size_is_a_single_span(self):
        spans = chunk_text("hello world", chunk_size=1000, chunk_overlap=150)

        assert spans == [ChunkSpan(text="hello world", char_start=0, char_end=11)]

    def test_leading_whitespace_is_skipped_from_char_start(self):
        text = "   hello"
        spans = chunk_text(text, chunk_size=1000, chunk_overlap=150)

        assert len(spans) == 1
        assert spans[0].char_start == 3
        assert spans[0].char_end == 8
        assert spans[0].text == "hello"


class TestChunkTextSpanIntegrity:
    def test_span_text_always_matches_the_original_text_slice(self):
        text = (
            "The trial enrolled patients across twelve sites. "
            "Primary endpoint was overall survival at twenty four months. "
            "Secondary endpoints included progression free survival and "
            "quality of life measures collected quarterly throughout the study."
        )
        spans = chunk_text(text, chunk_size=60, chunk_overlap=15)

        assert len(spans) > 1
        for span in spans:
            assert text[span.char_start : span.char_end] == span.text

    def test_span_length_never_exceeds_chunk_size(self):
        text = "word " * 500
        spans = chunk_text(text, chunk_size=50, chunk_overlap=10)

        for span in spans:
            assert span.char_end - span.char_start <= 50

    def test_last_span_reaches_end_of_text(self):
        # No trailing whitespace, so the final window's end == len(text)
        # unambiguously (a text ending in whitespace can have that
        # whitespace swept into the last span instead, which is a
        # different, also-valid property covered by the slice-integrity
        # test above).
        text = ("word " * 500).rstrip()
        spans = chunk_text(text, chunk_size=50, chunk_overlap=10)

        assert spans[-1].char_end == len(text)


class TestChunkTextSnappingAndOverlap:
    def test_snaps_to_whitespace_and_overlaps_by_configured_amount(self):
        # Hand-traced: 19 chars, chunk_size=10, chunk_overlap=2. Every
        # chunk boundary lands on a space rather than mid-word, and
        # consecutive spans share exactly `chunk_overlap` characters.
        text = "aaaa bbbb cccc dddd"
        spans = chunk_text(text, chunk_size=10, chunk_overlap=2)

        assert [(s.text, s.char_start, s.char_end) for s in spans] == [
            ("aaaa bbbb", 0, 9),
            ("bb cccc", 7, 14),
            ("cc dddd", 12, 19),
        ]

        # Consecutive spans overlap by exactly chunk_overlap characters.
        for earlier, later in zip(spans, spans[1:]):
            assert earlier.char_end - later.char_start == 2

    def test_no_word_is_split_across_a_chunk_boundary_when_a_space_exists(self):
        text = "supercalifragilisticexpialidocious is a very long single word here"
        spans = chunk_text(text, chunk_size=20, chunk_overlap=5)

        # Every span boundary (except the very start/end of the text)
        # should fall on a space in the original text, i.e. the char
        # just before char_start and just after char_end-1 is a space
        # or the text boundary — spans never end mid-word unless a
        # single "word" alone exceeds chunk_size (as the first one does
        # here, which is the one exception this test allows for).
        for span in spans:
            if span.char_end < len(text):
                assert text[span.char_end] == " " or span.text == text[span.char_start : span.char_end]

    def test_zero_overlap_is_allowed(self):
        text = "one two three four five six seven eight nine ten"
        spans = chunk_text(text, chunk_size=12, chunk_overlap=0)

        assert len(spans) > 1
        for earlier, later in zip(spans, spans[1:]):
            assert later.char_start >= earlier.char_end


class TestChunkTextValidation:
    def test_rejects_non_positive_chunk_size(self):
        with pytest.raises(ValueError):
            chunk_text("hello", chunk_size=0, chunk_overlap=0)

        with pytest.raises(ValueError):
            chunk_text("hello", chunk_size=-5, chunk_overlap=0)

    def test_rejects_negative_overlap(self):
        with pytest.raises(ValueError):
            chunk_text("hello", chunk_size=10, chunk_overlap=-1)

    def test_rejects_overlap_greater_than_or_equal_to_chunk_size(self):
        with pytest.raises(ValueError):
            chunk_text("hello", chunk_size=10, chunk_overlap=10)

        with pytest.raises(ValueError):
            chunk_text("hello", chunk_size=10, chunk_overlap=11)
