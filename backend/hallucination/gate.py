"""Confidence gate that refuses to answer when retrieval evidence is insufficient."""

import logging
from dataclasses import dataclass
from enum import Enum

from backend.config import get_settings
from backend.rag.fusion import RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()


class GateDecision(str, Enum):
    PASS = "pass"
    REFUSE = "refuse"


@dataclass
class GateResult:
    decision: GateDecision
    confidence: float
    reason: str | None = None
    closest_chunk: RetrievedChunk | None = None

    @property
    def passed(self) -> bool:
        return self.decision == GateDecision.PASS


class ConfidenceGate:

    def __init__(self, threshold: float | None = None,
                 soft_threshold: float | None = None):
        self.threshold = threshold or settings.confidence_threshold
        self.soft_threshold = soft_threshold or settings.soft_threshold

    def evaluate(
        self, top_score: float, n_chunks: int = 0,
        top_chunk: RetrievedChunk | None = None,
    ) -> GateResult:
        if n_chunks == 0:
            return GateResult(
                decision=GateDecision.REFUSE, confidence=0.0,
                reason="empty_corpus",
            )

        if top_score < self.threshold:
            logger.warning(
                f"Confidence gate REFUSED: score={top_score:.4f} < "
                f"threshold={self.threshold}"
            )
            return GateResult(
                decision=GateDecision.REFUSE, confidence=top_score,
                reason="low_confidence",
                closest_chunk=top_chunk if top_score >= self.soft_threshold else None,
            )

        logger.debug(f"Confidence gate PASSED: score={top_score:.4f}")
        return GateResult(decision=GateDecision.PASS, confidence=top_score)

    def refusal_message(self, gate_result: GateResult) -> str:
        base = {
            "low_confidence": (
                "I don't have reliable information about this in my official document "
                "corpus. Please consult the relevant government authority or official "
                "website for accurate guidance."
            ),
            "empty_corpus": (
                "No relevant official documents have been loaded for this jurisdiction "
                "yet. Please contact support."
            ),
        }.get(gate_result.reason or "", (
            "I cannot confidently answer this question from the available official "
            "sources. Please verify with the relevant authority."
        ))

        if gate_result.closest_chunk:
            c = gate_result.closest_chunk
            title = c.section_title or "Unknown section"
            content = (c.child_content or c.content)[:300]
            base += (
                f"\n\nThe closest information I found is about "
                f"\"{title}\":\n\n\"{content}\"\n\n"
                f"This may not be what you're looking for."
            )

        return base
