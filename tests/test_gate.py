"""Tests for hallucination/gate.py — pure logic."""
from backend.hallucination.gate import ConfidenceGate, GateDecision
from backend.rag.fusion import RetrievedChunk


def _chunk(score=0.5):
    return RetrievedChunk(id="c1", content="test", doc_id="d1",
                          score=score, section_title="Sec", child_content="child text")


class TestConfidenceGate:
    def setup_method(self):
        self.gate = ConfidenceGate(threshold=0.35, soft_threshold=0.15)

    def test_pass_above_threshold(self):
        result = self.gate.evaluate(0.8, n_chunks=5, top_chunk=_chunk(0.8))
        assert result.passed
        assert result.decision == GateDecision.PASS
        assert result.confidence == 0.8

    def test_refuse_below_threshold_above_soft(self):
        result = self.gate.evaluate(0.25, n_chunks=5, top_chunk=_chunk(0.25))
        assert not result.passed
        assert result.reason == "low_confidence"
        assert result.closest_chunk is not None

    def test_refuse_below_soft_threshold(self):
        result = self.gate.evaluate(0.05, n_chunks=5, top_chunk=_chunk(0.05))
        assert not result.passed
        assert result.reason == "low_confidence"
        assert result.closest_chunk is None

    def test_refuse_empty_corpus(self):
        result = self.gate.evaluate(0.0, n_chunks=0)
        assert not result.passed
        assert result.reason == "empty_corpus"

    def test_exact_threshold_refuses(self):
        # Score exactly at threshold — below means strictly less than
        result = self.gate.evaluate(0.34, n_chunks=3, top_chunk=_chunk(0.34))
        assert not result.passed

    def test_custom_thresholds(self):
        gate = ConfidenceGate(threshold=0.9, soft_threshold=0.5)
        result = gate.evaluate(0.85, n_chunks=3, top_chunk=_chunk(0.85))
        assert not result.passed


class TestRefusalMessage:
    def setup_method(self):
        self.gate = ConfidenceGate(threshold=0.35, soft_threshold=0.15)

    def test_low_confidence_message(self):
        result = self.gate.evaluate(0.05, n_chunks=3, top_chunk=_chunk(0.05))
        msg = self.gate.refusal_message(result)
        assert "reliable information" in msg.lower() or "don't have" in msg.lower()

    def test_empty_corpus_message(self):
        result = self.gate.evaluate(0.0, n_chunks=0)
        msg = self.gate.refusal_message(result)
        assert "no relevant" in msg.lower() or "loaded" in msg.lower()

    def test_includes_closest_chunk(self):
        result = self.gate.evaluate(0.25, n_chunks=3, top_chunk=_chunk(0.25))
        msg = self.gate.refusal_message(result)
        assert "closest" in msg.lower()
