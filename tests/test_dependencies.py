"""Tests for api/dependencies.py — Singleton pattern and RateLimiter."""
import pytest
import time
from unittest.mock import MagicMock
from fastapi import HTTPException
from backend.api.dependencies import Singleton, RateLimiter


class TestSingleton:
    def test_creates_instance_once(self):
        factory = MagicMock(return_value="instance")
        s = Singleton[str](factory)
        result1 = s.get()
        result2 = s.get()
        assert result1 == "instance"
        assert result2 == "instance"
        factory.assert_called_once()

    def test_different_singletons_independent(self):
        s1 = Singleton[int](lambda: 42)
        s2 = Singleton[str](lambda: "hello")
        assert s1.get() == 42
        assert s2.get() == "hello"

    def test_lazy_initialization(self):
        factory = MagicMock(return_value="lazy")
        s = Singleton[str](factory)
        factory.assert_not_called()
        s.get()
        factory.assert_called_once()


class TestRateLimiter:
    def test_allows_under_limit(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            limiter.check(user_id=1)  # should not raise

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        limiter.check(user_id=1)
        limiter.check(user_id=1)
        limiter.check(user_id=1)
        with pytest.raises(HTTPException) as exc_info:
            limiter.check(user_id=1)
        assert exc_info.value.status_code == 429

    def test_different_users_independent(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.check(user_id=1)
        limiter.check(user_id=1)
        # User 1 is at limit, but user 2 should be fine
        limiter.check(user_id=2)  # should not raise

    def test_window_expires(self):
        limiter = RateLimiter(max_requests=1, window_seconds=1)
        limiter.check(user_id=1)
        with pytest.raises(HTTPException):
            limiter.check(user_id=1)
        time.sleep(1.1)
        limiter.check(user_id=1)  # should not raise after window expires

    def test_error_message(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.check(user_id=1)
        with pytest.raises(HTTPException) as exc_info:
            limiter.check(user_id=1)
        assert "Rate limit" in exc_info.value.detail
