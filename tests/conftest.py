"""Shared fixtures for the BureauBot test suite."""
from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.rag.fusion import RetrievedChunk
from backend.db.models import Base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_chunk(id: str = "chunk-1", content: str = "test content",
               doc_id: str = "doc-1", score: float = 0.8,
               section_title: str = "Test Section", **kw) -> RetrievedChunk:
    return RetrievedChunk(id=id, content=content, doc_id=doc_id,
                          score=score, section_title=section_title,
                          metadata=kw.get("metadata", {"jurisdiction": "HU"}),
                          **{k: v for k, v in kw.items() if k != "metadata"})


# ---------------------------------------------------------------------------
# Mock retriever / reranker
# ---------------------------------------------------------------------------

class FakeRetriever:
    def __init__(self, chunks=None):
        self._chunks = chunks or [
            make_chunk("c1", "Residence permit renewal requires a passport photo.", "doc-1", 0.9, "Procedure"),
            make_chunk("c2", "TAJ card covers all health costs.", "doc-2", 0.7, "TAJ card"),
            make_chunk("c3", "Student ID via E066 Neptun request.", "doc-3", 0.6, "Student ID"),
        ]

    def retrieve(self, query, top_k=None, jurisdiction=None):
        return self._chunks, self._chunks

    def add_chunks(self, chunks):
        self._chunks.extend(chunks)

    def embed(self, texts):
        import numpy as np
        return np.ones((len(texts), 384), dtype="float32")


class FakeReranker:
    def __init__(self, score=0.85):
        self._score = score

    def rerank(self, query, chunks):
        for c in chunks:
            c.score = self._score
        return chunks[:5]

    def top_confidence(self, chunks):
        return max((c.score for c in chunks), default=0.0)


# ---------------------------------------------------------------------------
# Async SQLite DB fixtures (for route / integration tests)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(sqlite_engine):
    factory = async_sessionmaker(bind=sqlite_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Mock DB session for unit tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# httpx AsyncClient wired to FastAPI app with overrides
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(sqlite_engine):
    from backend.main import app
    from backend.api.dependencies import get_retriever, get_reranker
    from backend.db.session import get_db

    factory = async_sessionmaker(bind=sqlite_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever()
    app.dependency_overrides[get_reranker] = lambda: FakeReranker()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def auth_token(client: AsyncClient):
    res = await client.post("/api/v1/auth/register", json={
        "username": "testuser", "email": "test@example.com", "password": "testpass123",
    })
    return res.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}
