"""Tests for reciprocal rank fusion (app/retrieval/fusion.py).

Pure, no I/O, no third-party imports required by the code under test.
As with test_chunking.py, these assertions were also run directly
outside pytest as part of Phase 3 verification in an environment where
pytest itself isn't installed.
"""

import pytest

from app.retrieval.fusion import FusedResult, reciprocal_rank_fusion


class TestReciprocalRankFusionBasics:
    def test_empty_rankings_produce_no_results(self):
        assert reciprocal_rank_fusion([]) == []

    def test_single_empty_ranking_produces_no_results(self):
        assert reciprocal_rank_fusion([[]]) == []

    def test_single_ranking_preserves_order(self):
        fused = reciprocal_rank_fusion([[10, 20, 30]], k=60)

        assert [r.item_id for r in fused] == [10, 20, 30]
        assert fused[0].score == pytest.approx(1 / 61)
        assert fused[1].score == pytest.approx(1 / 62)
        assert fused[2].score == pytest.approx(1 / 63)

    def test_duplicates_within_one_list_count_only_once_at_first_occurrence(self):
        fused = reciprocal_rank_fusion([[5, 5, 5, 7]], k=60)

        assert [r.item_id for r in fused] == [5, 7]
        # 5 is credited only for its first (best) occurrence, at
        # position 1 — not summed across all three appearances.
        assert fused[0].score == pytest.approx(1 / 61)
        # Rank is the item's position in the list, duplicates included:
        # 7 is the 4th element, so it scores as rank 4, not rank 2.
        assert fused[1].score == pytest.approx(1 / 64)


class TestReciprocalRankFusionCombining:
    def test_agreement_across_lists_outranks_a_single_list_top_hit(self):
        # Item 3 is dead last (rank 3) in both lists; items 1 and 2 swap
        # rank 1/2 between the two lists. By symmetry 1 and 2 should tie
        # and both outscore 3.
        list_a = [1, 2, 3]
        list_b = [2, 1, 3]

        fused = reciprocal_rank_fusion([list_a, list_b], k=60)
        by_id = {r.item_id: r.score for r in fused}

        assert by_id[1] == pytest.approx(by_id[2])
        assert by_id[1] > by_id[3]
        assert by_id[3] == pytest.approx(1 / 63 + 1 / 63)

    def test_item_found_by_both_retrievers_beats_item_found_by_only_one(self):
        # Item 99 ranks worse in each individual list than item 1 does in
        # its one appearance, but appearing in *both* lists should still
        # let it win once both signals are combined and considered
        # relative to a same-single-list comparison.
        list_a = [99, 1]  # 1 is rank 2, worse than 99 in this list
        list_b = [99]  # 1 doesn't appear at all here

        fused = reciprocal_rank_fusion([list_a, list_b], k=60)
        by_id = {r.item_id: r.score for r in fused}

        assert by_id[99] == pytest.approx(1 / 61 + 1 / 61)
        assert by_id[1] == pytest.approx(1 / 62)
        assert by_id[99] > by_id[1]

    def test_source_ranks_records_which_lists_and_at_what_rank(self):
        list_a = [1, 2]
        list_b = [2, 1]

        fused = reciprocal_rank_fusion([list_a, list_b], k=60)
        by_id = {r.item_id: r.source_ranks for r in fused}

        assert by_id[1] == {0: 1, 1: 2}
        assert by_id[2] == {0: 2, 1: 1}

    def test_results_are_sorted_descending_by_score(self):
        fused = reciprocal_rank_fusion([[3, 1, 2], [1, 2, 3]], k=60)

        scores = [r.score for r in fused]
        assert scores == sorted(scores, reverse=True)

    def test_returns_fusedresult_instances(self):
        fused = reciprocal_rank_fusion([[1]], k=60)

        assert len(fused) == 1
        assert isinstance(fused[0], FusedResult)


class TestReciprocalRankFusionValidation:
    def test_rejects_non_positive_k(self):
        with pytest.raises(ValueError):
            reciprocal_rank_fusion([[1, 2]], k=0)

        with pytest.raises(ValueError):
            reciprocal_rank_fusion([[1, 2]], k=-1)
