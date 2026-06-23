"""Dependency injection: Singleton factory, rate limiter, and auth guards for FastAPI routes."""
import time
from collections import defaultdict
from functools import lru_cache
from typing import TypeVar, Generic, Callable

from fastapi import Depends, HTTPException
from backend.rag.retriever import HybridRetriever
from backend.rag.reranker import CrossEncoderReranker
from backend.services.auth import get_current_user
from backend.db.models import User

T = TypeVar("T")


class Singleton(Generic[T]):
    """Generic singleton container — parametric polymorphism."""

    def __init__(self, factory: Callable[[], T]):
        self._instance: T | None = None
        self._factory = factory

    def get(self) -> T:
        if self._instance is None:
            self._instance = self._factory()
        return self._instance


_retriever = Singleton[HybridRetriever](HybridRetriever)
_reranker = Singleton[CrossEncoderReranker](CrossEncoderReranker)


def get_retriever() -> HybridRetriever:
    return _retriever.get()


def get_reranker() -> CrossEncoderReranker:
    return _reranker.get()


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._requests: dict[int, list[float]] = defaultdict(list)

    def check(self, user_id: int) -> None:
        now = time.time()
        timestamps = self._requests[user_id]
        self._requests[user_id] = [t for t in timestamps if now - t < self._window]
        if len(self._requests[user_id]) >= self._max:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a moment.")
        self._requests[user_id].append(now)


_rate_limiter = RateLimiter()


def check_rate_limit(user: User = Depends(get_current_user)) -> User:
    _rate_limiter.check(user.id)
    return user
