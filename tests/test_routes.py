"""Integration tests for API routes — httpx + SQLite in-memory DB."""
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tests.conftest import FakeRetriever, FakeReranker, make_chunk


class _FakeStream:
    """Async iterator mimicking Gemini stream response."""
    def __init__(self, chunks):
        self._chunks = chunks
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._chunks):
            raise StopAsyncIteration
        c = self._chunks[self._i]
        self._i += 1
        return c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    @pytest.mark.asyncio
    async def test_health(self, client):
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_register(self, client):
        res = await client.post("/api/v1/auth/register", json={
            "username": "newuser", "email": "new@test.com", "password": "pass123",
        })
        assert res.status_code == 200
        assert "access_token" in res.json()

    @pytest.mark.asyncio
    async def test_register_duplicate(self, client):
        payload = {"username": "dup", "email": "dup@test.com", "password": "pass123"}
        await client.post("/api/v1/auth/register", json=payload)
        res = await client.post("/api/v1/auth/register", json=payload)
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_login_valid(self, client):
        await client.post("/api/v1/auth/register", json={
            "username": "loginuser", "email": "login@test.com", "password": "pass123",
        })
        res = await client.post("/api/v1/auth/login", json={
            "username": "loginuser", "password": "pass123",
        })
        assert res.status_code == 200
        assert "access_token" in res.json()

    @pytest.mark.asyncio
    async def test_login_invalid(self, client):
        res = await client.post("/api/v1/auth/login", json={
            "username": "nobody", "password": "wrong",
        })
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Chat (requires auth + mocked LLM)
# ---------------------------------------------------------------------------

class TestChat:
    @pytest.mark.asyncio
    async def test_chat_requires_auth(self, client):
        res = await client.post("/api/v1/chat", json={"message": "hello"})
        assert res.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_chat_blocking(self, client, auth_token):
        with patch("backend.services.chat.genai.Client") as MockClient:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = "Mocked response"

            mock_client.aio.models.generate_content_stream = AsyncMock(return_value=_FakeStream([mock_resp]))
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=MagicMock(text="variant")
            )
            MockClient.return_value = mock_client

            res = await client.post("/api/v1/chat", json={"message": "test question"},
                                    headers={"Authorization": f"Bearer {auth_token}"})
            assert res.status_code == 200
            data = res.json()
            assert "session_id" in data
            assert len(data["message"]) > 0

    @pytest.mark.asyncio
    async def test_chat_stream_sse(self, client, auth_token):
        with patch("backend.services.chat.genai.Client") as MockClient:
            mock_client = MagicMock()
            mock_chunk = MagicMock()
            mock_chunk.text = "streamed token"

            mock_client.aio.models.generate_content_stream = AsyncMock(return_value=_FakeStream([mock_chunk]))
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=MagicMock(text="variant")
            )
            MockClient.return_value = mock_client

            res = await client.post("/api/v1/chat/stream",
                                    json={"message": "test"},
                                    headers={"Authorization": f"Bearer {auth_token}"})
            assert res.status_code == 200
            body = res.text
            assert "event: session" in body
            assert "event: done" in body

    @pytest.mark.asyncio
    async def test_low_confidence_refusal(self, client, auth_token, sqlite_engine):
        """Low-confidence query returns structured refusal, not 500."""
        from backend.main import app
        from backend.api.dependencies import get_reranker
        app.dependency_overrides[get_reranker] = lambda: FakeReranker(score=0.05)

        with patch("backend.services.chat.genai.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=MagicMock(text="variant")
            )
            MockClient.return_value = mock_client

            res = await client.post("/api/v1/chat",
                                    json={"message": "something unknown"},
                                    headers={"Authorization": f"Bearer {auth_token}"})
            assert res.status_code == 200
            assert "don't have" in res.json()["message"].lower() or "cannot" in res.json()["message"].lower()

        app.dependency_overrides[get_reranker] = lambda: FakeReranker()


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

class TestIngest:
    @pytest.mark.asyncio
    async def test_ingest_document(self, client, auth_token):
        res = await client.post("/api/v1/ingest", json={
            "text": "x" * 100,
            "title": "Test Document",
            "jurisdiction": "HU",
        }, headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "doc_id" in data
        assert data["title"] == "Test Document"


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class TestSessions:
    @pytest.mark.asyncio
    async def test_history_not_found(self, client, auth_token):
        res = await client.get("/api/v1/sessions/nonexistent/history",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

class TestDocuments:
    @pytest.mark.asyncio
    async def test_list_documents(self, client, auth_token):
        res = await client.get("/api/v1/documents",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        assert isinstance(res.json(), list)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class TestErrors:
    @pytest.mark.asyncio
    async def test_list_errors(self, client, auth_token):
        res = await client.get("/api/v1/admin/errors",
                               headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        assert isinstance(res.json(), list)


# ---------------------------------------------------------------------------
# Flag
# ---------------------------------------------------------------------------

class TestFlag:
    @pytest.mark.asyncio
    async def test_flag_answer(self, client, auth_token):
        res = await client.post("/api/v1/chat/flag", json={
            "session_id": "s1", "turn_id": 1, "category": "wrong_info",
        }, headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        assert "flag" in res.json()["message"].lower() or "thank" in res.json()["message"].lower()
