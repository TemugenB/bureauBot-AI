"""Tests for services/chat.py — mock LLM, retriever, reranker, DB."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.conftest import FakeRetriever, FakeReranker, make_chunk


def _mock_db(session_exists=False, turns=None):
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    if session_exists:
        from backend.db.models import Session as SessionModel
        s = MagicMock(spec=SessionModel)
        s.id = "existing-session"
        s.jurisdiction = "HU"
        db.get = AsyncMock(return_value=s)
    else:
        db.get = AsyncMock(return_value=None)

    mock_result = MagicMock()
    mock_result.scalar.return_value = len(turns) if turns else 0
    mock_result.scalars.return_value.all.return_value = turns or []
    db.execute = AsyncMock(return_value=mock_result)
    return db


class _FakeStreamChunk:
    def __init__(self, text):
        self.text = text


class _FakeAsyncStream:
    """Async iterator that mimics the Gemini stream response."""
    def __init__(self, tokens=None, error=None):
        self._tokens = tokens or ["Hello", " world"]
        self._error = error
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._error and self._index >= 1:
            raise self._error
        if self._index >= len(self._tokens):
            raise StopAsyncIteration
        chunk = _FakeStreamChunk(self._tokens[self._index])
        self._index += 1
        return chunk


def _fake_client(tokens=None, error=None):
    """Create a mock that mimics google.genai.Client."""
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(
        return_value=_FakeAsyncStream(tokens, error)
    )
    client.aio.models.generate_content = AsyncMock(
        return_value=MagicMock(text="expanded query variant")
    )
    return client


def _build_service(db, retriever=None, reranker=None, tokens=None, error=None):
    """Build a ChatService with the genai.Client constructor mocked."""
    fake = _fake_client(tokens=tokens, error=error)
    with patch("backend.services.chat.genai.Client", return_value=fake):
        from backend.services.chat import ChatService
        service = ChatService(
            retriever=retriever or FakeRetriever(),
            reranker=reranker or FakeReranker(),
            db=db,
        )
    # Belt-and-suspenders: ensure _client is our fake
    service._client = fake
    return service


class TestGetOrCreateSession:
    @pytest.mark.asyncio
    async def test_creates_new_session(self):
        db = _mock_db(session_exists=False)
        service = _build_service(db)
        sid = await service.get_or_create_session(None, "HU")
        assert len(sid) == 36
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_existing_session(self):
        db = _mock_db(session_exists=True)
        service = _build_service(db)
        sid = await service.get_or_create_session("existing-session", "HU")
        assert sid == "existing-session"


class TestStreamResponse:
    @pytest.mark.asyncio
    async def test_yields_tokens(self):
        db = _mock_db()
        service = _build_service(db, tokens=["Hello", " world"])
        tokens = []
        async for t in service.stream_response("s1", "test question"):
            tokens.append(t)
        full = "".join(tokens)
        assert "Hello" in full

    @pytest.mark.asyncio
    async def test_refuses_on_low_confidence(self):
        db = _mock_db()
        service = _build_service(db, reranker=FakeReranker(score=-3.0))
        tokens = []
        async for t in service.stream_response("s1", "unknown topic"):
            tokens.append(t)
        full = "".join(tokens)
        assert "don't have reliable" in full.lower() or "cannot" in full.lower()

    @pytest.mark.asyncio
    async def test_error_mid_stream(self):
        from google.genai import errors as genai_errors
        db = _mock_db()

        error = genai_errors.ClientError(400, {"error": {"message": "quota exceeded"}})
        fake = _fake_client(tokens=["partial ", "more"], error=error)

        with patch("backend.services.chat.genai.Client", return_value=fake):
            from backend.services.chat import ChatService
            service = ChatService(FakeRetriever(), FakeReranker(), db)
        service._client = fake

        tokens = []
        async for t in service.stream_response("s1", "test"):
            tokens.append(t)
        full = "".join(tokens)
        assert "[ERROR]" in full
        assert "partial response" in full.lower()

    @pytest.mark.asyncio
    async def test_persists_turn_on_success(self):
        db = _mock_db()
        service = _build_service(db, tokens=["response text"])
        async for _ in service.stream_response("s1", "test"):
            pass
        assert db.add.called
        assert db.commit.await_count >= 1
