"""Unit tests for app/evaluation/metrics.py — pure functions, no I/O.

Written as ordinary pytest, matching every other pure-logic test file in
this suite (test_chunking.py, test_fusion.py, test_citations.py, etc.).
See docs/phase-6-notes.md for how these assertions were additionally
executed directly in this sandbox (pytest itself isn't installed here),
via a standalone runner that imports this exact module and calls each
test function/method by hand.
"""

import pytest

from app.evaluation.metrics import (
    ConfusionCounts,
    abstention_accuracy,
    abstention_confusion_counts,
    citation_completeness,
    citation_correctness,
    mean_reciprocal_rank,
    mean_recall_at_k,
    recall_at_k,
    reciprocal_rank,
)


class TestRecallAtK:
    def test_all_relevant_found_in_top_k(self):
        assert recall_at_k(["a", "b", "c"], {"a", "c"}, k=3) == 1.0

    def test_partial_recall(self):
        assert recall_at_k(["a", "x", "y"], {"a", "b"}, k=3) == 0.5

    def test_relevant_item_outside_top_k_not_counted(self):
        assert recall_at_k(["x", "y", "a"], {"a"}, k=2) == 0.0

    def test_empty_relevant_set_is_vacuously_1(self):
        assert recall_at_k(["a", "b"], set(), k=5) == 1.0

    def test_empty_retrieved_list_is_zero(self):
        assert recall_at_k([], {"a"}, k=5) == 0.0

    def test_duplicate_retrieved_ids_do_not_inflate_score(self):
        assert recall_at_k(["a", "a", "a"], {"a", "b"}, k=3) == 0.5

    def test_negative_k_raises(self):
        with pytest.raises(ValueError):
            recall_at_k(["a"], {"a"}, k=-1)

    def test_k_zero_never_recalls_anything(self):
        assert recall_at_k(["a", "b"], {"a"}, k=0) == 0.0


class TestReciprocalRank:
    def test_first_result_is_relevant(self):
        assert reciprocal_rank(["a", "b"], {"a"}) == 1.0

    def test_relevant_item_at_rank_three(self):
        assert reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)

    def test_no_relevant_item_found_is_zero(self):
        assert reciprocal_rank(["x", "y"], {"a"}) == 0.0

    def test_empty_relevant_set_is_zero(self):
        assert reciprocal_rank(["a", "b"], set()) == 0.0

    def test_uses_first_match_not_best_match(self):
        # "b" appears at rank 1 and is relevant; "a" at rank 2 is also
        # relevant but shouldn't change the result — first match wins.
        assert reciprocal_rank(["b", "a"], {"a", "b"}) == 1.0


class TestMeanAggregates:
    def test_mean_recall_at_k_averages_across_questions(self):
        pairs = [
            (["a", "b"], {"a"}),  # recall 1.0
            (["x", "y"], {"a"}),  # recall 0.0
        ]
        assert mean_recall_at_k(pairs, k=2) == 0.5

    def test_mean_recall_at_k_empty_raises(self):
        with pytest.raises(ValueError):
            mean_recall_at_k([], k=5)

    def test_mean_reciprocal_rank_averages_across_questions(self):
        pairs = [
            (["a"], {"a"}),  # RR 1.0
            (["x", "a"], {"a"}),  # RR 0.5
        ]
        assert mean_reciprocal_rank(pairs) == pytest.approx(0.75)

    def test_mean_reciprocal_rank_empty_raises(self):
        with pytest.raises(ValueError):
            mean_reciprocal_rank([])


class TestCitationCorrectness:
    def test_all_cited_are_relevant(self):
        assert citation_correctness(["A", "B"], {"A", "B", "C"}) == 1.0

    def test_some_cited_are_irrelevant(self):
        assert citation_correctness(["A", "X"], {"A"}) == 0.5

    def test_none_cited_and_none_relevant_is_correct(self):
        assert citation_correctness([], set()) == 1.0

    def test_none_cited_but_something_was_relevant_is_incorrect(self):
        assert citation_correctness([], {"A"}) == 0.0

    def test_duplicate_citations_do_not_double_count(self):
        assert citation_correctness(["A", "A"], {"A"}) == 1.0


class TestCitationCompleteness:
    def test_all_relevant_were_cited(self):
        assert citation_completeness(["A", "B"], {"A", "B"}) == 1.0

    def test_only_some_relevant_were_cited(self):
        assert citation_completeness(["A"], {"A", "B"}) == 0.5

    def test_nothing_relevant_is_vacuously_complete(self):
        assert citation_completeness(["A", "B"], set()) == 1.0

    def test_nothing_cited_when_something_was_relevant(self):
        assert citation_completeness([], {"A"}) == 0.0


class TestAbstentionAccuracy:
    def test_all_correct(self):
        predictions = [(True, True), (False, False), (True, True)]
        assert abstention_accuracy(predictions) == 1.0

    def test_all_wrong(self):
        predictions = [(True, False), (False, True)]
        assert abstention_accuracy(predictions) == 0.0

    def test_mixed(self):
        predictions = [(True, True), (True, False), (False, False), (False, True)]
        assert abstention_accuracy(predictions) == 0.5

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            abstention_accuracy([])


class TestAbstentionConfusionCounts:
    def test_categorizes_each_quadrant(self):
        predictions = [
            (True, True),  # TP
            (False, True),  # FP: answered a trap question
            (False, False),  # TN
            (True, False),  # FN: abstained on an answerable question
        ]
        counts = abstention_confusion_counts(predictions)
        assert counts == ConfusionCounts(true_positive=1, false_positive=1, true_negative=1, false_negative=1)
        assert counts.total == 4
        assert counts.accuracy == 0.5

    def test_accuracy_matches_abstention_accuracy(self):
        predictions = [(True, True), (True, True), (False, False), (True, False)]
        counts = abstention_confusion_counts(predictions)
        assert counts.accuracy == abstention_accuracy(predictions)

    def test_accuracy_raises_on_zero_total(self):
        with pytest.raises(ValueError):
            ConfusionCounts(0, 0, 0, 0).accuracy
