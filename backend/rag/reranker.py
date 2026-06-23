"""Cross-encoder reranker: re-scores retrieved chunks by query relevance and returns top-k."""

import logging
from sentence_transformers import CrossEncoder
from backend.config import get_settings
from backend.rag.fusion import RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()


class CrossEncoderReranker:

    def __init__(
        self,
        model_name: str | None = None,
        top_k: int | None = None,
    ):
        model_name = model_name or settings.reranker_model
        self.top_k = top_k or settings.rerank_top_k
        logger.info(f"Loading cross-encoder: {model_name}")
        self._model = CrossEncoder(model_name, max_length=512)

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []

        pairs = [(query, c.content) for c in chunks]

        try:
            scores = self._model.predict(pairs, show_progress_bar=False)
        except Exception as exc:
            logger.error(f"Cross-encoder prediction failed: {exc}")
            # Graceful degradation — return the top-k from the pre-ranked list
            return chunks[: self.top_k]

        scored = sorted(
            zip(scores, chunks),
            key=lambda x: float(x[0]),
            reverse=True,
        )

        top_chunks = []
        for score, chunk in scored[: self.top_k]:
            chunk.score = float(score)
            top_chunks.append(chunk)

        logger.debug(
            f"Reranked {len(chunks)} → {len(top_chunks)} chunks. "
            f"Top score: {top_chunks[0].score:.4f}"
        )
        return top_chunks

    def top_confidence(self, chunks: list[RetrievedChunk]) -> float:
        if not chunks:
            return 0.0
        return max(c.score for c in chunks)
