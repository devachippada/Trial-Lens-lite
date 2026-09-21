"""Tests for app.ingestion.dedup — pure logic, no fixtures needed."""

from app.ingestion.dedup import DedupAction, classify_by_source_id, find_hash_collisions


class TestClassifyBySourceId:
    def test_no_existing_row_is_new(self):
        result = classify_by_source_id(existing_id=None, existing_content_hash=None, new_content_hash="abc")

        assert result.action == DedupAction.NEW
        assert result.existing_id is None

    def test_same_hash_is_unchanged(self):
        result = classify_by_source_id(existing_id=42, existing_content_hash="abc", new_content_hash="abc")

        assert result.action == DedupAction.UNCHANGED
        assert result.existing_id == 42

    def test_different_hash_is_updated(self):
        result = classify_by_source_id(existing_id=42, existing_content_hash="abc", new_content_hash="def")

        assert result.action == DedupAction.UPDATED
        assert result.existing_id == 42


class TestFindHashCollisions:
    def test_no_collisions_when_all_unique(self):
        collisions = find_hash_collisions({"NCT1": "hash1", "NCT2": "hash2"})
        assert collisions == {}

    def test_detects_two_source_ids_sharing_a_hash(self):
        collisions = find_hash_collisions({"NCT1": "hashA", "NCT2": "hashA", "NCT3": "hashB"})
        assert collisions == {"hashA": ["NCT1", "NCT2"]}

    def test_detects_larger_group(self):
        collisions = find_hash_collisions(
            {"PMID1": "same", "PMID2": "same", "PMID3": "same", "PMID4": "different"}
        )
        assert collisions == {"same": ["PMID1", "PMID2", "PMID3"]}

    def test_empty_input(self):
        assert find_hash_collisions({}) == {}
