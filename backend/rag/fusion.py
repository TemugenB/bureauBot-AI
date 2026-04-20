from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from backend.config import get_settings

settings = get_settings()


@dataclass
class RetrievedChunk:
    id: str
    content: str
    doc_id: str
    score: float = 0.0
    bm25_score: float = 0.0
    parent_content: str = ""
    section_title: str = ""
    child_content: str = ""
    metadata: dict = field(default_factory=dict)


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    k: int | None = None,
) -> list[RetrievedChunk]:
    k = k or settings.rrf_k
    rrf_scores: dict[str, float] = defaultdict(float)
    chunk_registry: dict[str, RetrievedChunk] = {}

    for ranked_list in ranked_lists:
        for rank, chunk in enumerate(ranked_list, start=1):
            rrf_scores[chunk.id] += 1.0 / (k + rank)
            if chunk.id not in chunk_registry:
                chunk_registry[chunk.id] = chunk

    fused: list[RetrievedChunk] = []
    for chunk_id, rrf_score in rrf_scores.items():
        chunk = chunk_registry[chunk_id]
        chunk.score = rrf_score
        fused.append(chunk)

    fused.sort(key=lambda c: c.score, reverse=True)
    return fused


def _score_normalise(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    if not chunks:
        return chunks
    scores = [c.score for c in chunks]
    lo, hi = min(scores), max(scores)
    span = hi - lo or 1.0
    for c in chunks:
        c.score = (c.score - lo) / span
    return chunks


def hybrid_score(
    dense_chunks: list[RetrievedChunk],
    bm25_chunks: list[RetrievedChunk],
    alpha: float = 0.5,
) -> list[RetrievedChunk]:
    dense_chunks = _score_normalise(list(dense_chunks))
    bm25_chunks = _score_normalise(list(bm25_chunks))

    dense_map = {c.id: c.score for c in dense_chunks}
    bm25_map = {c.id: c.bm25_score for c in bm25_chunks}

    all_ids = set(dense_map) | set(bm25_map)
    combined: dict[str, RetrievedChunk] = {}

    chunk_lookup = {c.id: c for c in dense_chunks + bm25_chunks}

    for cid in all_ids:
        chunk = chunk_lookup[cid]
        d_score = dense_map.get(cid, 0.0)
        b_score = bm25_map.get(cid, 0.0)
        chunk.score = alpha * d_score + (1 - alpha) * b_score
        combined[cid] = chunk

    result = list(combined.values())
    result.sort(key=lambda c: c.score, reverse=True)
    return result
