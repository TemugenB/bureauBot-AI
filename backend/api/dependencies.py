from __future__ import annotations

from functools import lru_cache
from backend.rag.retriever import HybridRetriever
from backend.rag.reranker import CrossEncoderReranker


@lru_cache(maxsize=1)
def _retriever_singleton() -> HybridRetriever:
    return HybridRetriever()


@lru_cache(maxsize=1)
def _reranker_singleton() -> CrossEncoderReranker:
    return CrossEncoderReranker()


def get_retriever() -> HybridRetriever:
    return _retriever_singleton()


def get_reranker() -> CrossEncoderReranker:
    return _reranker_singleton()
