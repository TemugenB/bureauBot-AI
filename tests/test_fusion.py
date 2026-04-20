"""Tests for rag/fusion.py — pure logic, no external deps."""
from backend.rag.fusion import (
    RetrievedChunk, reciprocal_rank_fusion, hybrid_score, _score_normalise,
)


def _chunk(id, score=0.0, bm25=0.0):
    return RetrievedChunk(id=id, content=f"text-{id}", doc_id="d1",
                          score=score, bm25_score=bm25)


class TestReciprocalRankFusion:
    def test_merges_multiple_lists(self):
        list1 = [_chunk("a"), _chunk("b")]
        list2 = [_chunk("b"), _chunk("c")]
        result = reciprocal_rank_fusion([list1, list2])
        ids = [c.id for c in result]
        assert "a" in ids and "b" in ids and "c" in ids
        # "b" appears in both lists so should have highest RRF score
        assert result[0].id == "b"

    def test_empty_lists(self):
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[], []]) == []

    def test_deduplicates_across_lists(self):
        list1 = [_chunk("a")]
        list2 = [_chunk("a")]
        result = reciprocal_rank_fusion([list1, list2])
        assert len(result) == 1

    def test_single_list(self):
        chunks = [_chunk("x"), _chunk("y")]
        result = reciprocal_rank_fusion([chunks])
        assert len(result) == 2


class TestHybridScore:
    def test_blends_scores(self):
        dense = [_chunk("a", score=1.0), _chunk("b", score=0.0)]
        bm25 = [_chunk("a", bm25=0.0), _chunk("b", bm25=1.0)]
        result = hybrid_score(dense, bm25, alpha=0.5)
        scores = {c.id: c.score for c in result}
        assert abs(scores["a"] - scores["b"]) < 0.01  # both ~0.5

    def test_non_overlapping_sets(self):
        dense = [_chunk("a", score=1.0)]
        bm25 = [_chunk("b", bm25=1.0)]
        result = hybrid_score(dense, bm25, alpha=0.5)
        assert len(result) == 2


class TestScoreNormalise:
    def test_single_element(self):
        chunks = [_chunk("a", score=5.0)]
        result = _score_normalise(chunks)
        assert result[0].score == 0.0  # (5-5)/(5-5) → 0/1 = 0

    def test_identical_scores(self):
        chunks = [_chunk("a", score=3.0), _chunk("b", score=3.0)]
        result = _score_normalise(chunks)
        assert all(c.score == 0.0 for c in result)

    def test_normalises_range(self):
        chunks = [_chunk("a", score=0.0), _chunk("b", score=10.0)]
        result = _score_normalise(chunks)
        scores = {c.id: c.score for c in result}
        assert scores["a"] == 0.0
        assert scores["b"] == 1.0

    def test_empty(self):
        assert _score_normalise([]) == []
