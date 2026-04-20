"""Tests for rag/reranker.py — mock CrossEncoder model."""
import numpy as np
from unittest.mock import patch, MagicMock
from backend.rag.fusion import RetrievedChunk


def _chunk(id, content="text"):
    return RetrievedChunk(id=id, content=content, doc_id="d1")


def _make_reranker(scores=None, top_k=3, fail=False):
    """Create a CrossEncoderReranker with a mocked model."""
    with patch("backend.rag.reranker.CrossEncoder") as MockCE:
        mock_model = MagicMock()
        if fail:
            mock_model.predict.side_effect = RuntimeError("model error")
        else:
            mock_model.predict.return_value = np.array(scores or [])
        MockCE.return_value = mock_model

        from backend.rag.reranker import CrossEncoderReranker
        reranker = CrossEncoderReranker(model_name="mock", top_k=top_k)
        reranker._model = mock_model
        return reranker


class TestRerank:
    def test_sorts_by_score_descending(self):
        reranker = _make_reranker(scores=[0.1, 0.9, 0.5], top_k=3)
        chunks = [_chunk("a"), _chunk("b"), _chunk("c")]
        result = reranker.rerank("query", chunks)
        assert result[0].id == "b"
        assert result[1].id == "c"
        assert result[2].id == "a"

    def test_returns_top_k_only(self):
        reranker = _make_reranker(scores=[0.9, 0.8, 0.7, 0.6, 0.5], top_k=2)
        chunks = [_chunk(f"c{i}") for i in range(5)]
        result = reranker.rerank("query", chunks)
        assert len(result) == 2

    def test_graceful_degradation_on_failure(self):
        reranker = _make_reranker(fail=True, top_k=2)
        chunks = [_chunk("a"), _chunk("b"), _chunk("c")]
        result = reranker.rerank("query", chunks)
        assert len(result) == 2
        assert result[0].id == "a"  # pre-ranked order preserved

    def test_empty_chunks(self):
        reranker = _make_reranker(scores=[], top_k=3)
        result = reranker.rerank("query", [])
        assert result == []

    def test_scores_assigned_to_chunks(self):
        reranker = _make_reranker(scores=[0.42, 0.88], top_k=2)
        chunks = [_chunk("a"), _chunk("b")]
        result = reranker.rerank("query", chunks)
        assert result[0].score == 0.88
        assert result[1].score == 0.42


class TestTopConfidence:
    def test_returns_max(self):
        reranker = _make_reranker(top_k=3)
        chunks = [_chunk("a"), _chunk("b")]
        chunks[0].score = 0.3
        chunks[1].score = 0.9
        assert reranker.top_confidence(chunks) == 0.9

    def test_empty_returns_zero(self):
        reranker = _make_reranker(top_k=3)
        assert reranker.top_confidence([]) == 0.0
