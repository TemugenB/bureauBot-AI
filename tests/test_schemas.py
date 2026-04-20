"""Tests for api/schemas.py — Pydantic validation."""
import pytest
from pydantic import ValidationError
from backend.api.schemas import (
    ChatRequest, IngestRequest, FlagRequest, RegisterRequest,
    HealthResponse, ChatResponse, TokenResponse,
)


class TestChatRequest:
    def test_valid(self):
        r = ChatRequest(message="Hello")
        assert r.message == "Hello"
        assert r.jurisdiction == "HU"
        assert r.session_id is None

    def test_rejects_empty_message(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_rejects_too_long(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="x" * 2001)

    def test_custom_jurisdiction(self):
        r = ChatRequest(message="hi", jurisdiction="DE")
        assert r.jurisdiction == "DE"


class TestIngestRequest:
    def test_rejects_short_text(self):
        with pytest.raises(ValidationError):
            IngestRequest(text="too short", title="T")

    def test_valid(self):
        r = IngestRequest(text="x" * 60, title="Doc Title")
        assert r.jurisdiction == "HU"


class TestFlagRequest:
    def test_valid_categories(self):
        for cat in ["wrong_info", "outdated", "incomplete", "other"]:
            r = FlagRequest(session_id="s1", turn_id=1, category=cat)
            assert r.category == cat

    def test_rejects_invalid_category(self):
        with pytest.raises(ValidationError):
            FlagRequest(session_id="s1", turn_id=1, category="invalid")


class TestRegisterRequest:
    def test_rejects_short_username(self):
        with pytest.raises(ValidationError):
            RegisterRequest(username="ab", email="a@b.com", password="123456")

    def test_rejects_short_password(self):
        with pytest.raises(ValidationError):
            RegisterRequest(username="alice", email="a@b.com", password="12345")

    def test_valid(self):
        r = RegisterRequest(username="alice", email="a@b.com", password="secret123")
        assert r.username == "alice"


class TestResponseDefaults:
    def test_health(self):
        r = HealthResponse()
        assert r.status == "ok"
        assert r.version == "1.0.0"

    def test_token(self):
        r = TokenResponse(access_token="abc")
        assert r.token_type == "bearer"

    def test_chat(self):
        r = ChatResponse(session_id="s1", message="hi")
        assert r.session_id == "s1"
