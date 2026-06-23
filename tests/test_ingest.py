"""Tests for services/ingest.py — mock retriever and DB."""
import pytest
from unittest.mock import AsyncMock, MagicMock, call
from backend.services.ingest import IngestService


def _mock_retriever():
    r = MagicMock()
    r.add_chunks = MagicMock()
    return r


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = None
    db.execute = AsyncMock(return_value=mock_result)
    return db


SAMPLE_TEXT = """Procedure:
You need to prepare the following documents for the online application.

Required documents:
- A passport-size photo
- Your Letter of Award
- Proof of health insurance
- Transcript of academic records

Additional info:
If you are on an extension semester, proof of means of subsistence is required.
"""


class TestIngestService:
    @pytest.mark.asyncio
    async def test_ingest_returns_uuid(self):
        service = IngestService(retriever=_mock_retriever(), db=_mock_db())
        doc_id = await service.ingest(text=SAMPLE_TEXT, title="Test Doc")
        assert len(doc_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_calls_add_chunks(self):
        retriever = _mock_retriever()
        service = IngestService(retriever=retriever, db=_mock_db())
        await service.ingest(text=SAMPLE_TEXT, title="Test Doc")
        retriever.add_chunks.assert_called_once()
        chunks = retriever.add_chunks.call_args[0][0]
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_embeds_children_not_parents(self):
        retriever = _mock_retriever()
        service = IngestService(retriever=retriever, db=_mock_db())
        await service.ingest(text=SAMPLE_TEXT, title="Test Doc")
        embedded = retriever.add_chunks.call_args[0][0]
        # Children have non-None parent_content or metadata with parent_id
        for c in embedded:
            assert c.metadata.get("parent_id", "") != "" or c.parent_content

    @pytest.mark.asyncio
    async def test_persists_document_and_chunks(self):
        db = _mock_db()
        service = IngestService(retriever=_mock_retriever(), db=db)
        await service.ingest(text=SAMPLE_TEXT, title="Test Doc",
                             jurisdiction="HU", task_category="residence")
        # db.add should be called multiple times (Document + chunks)
        assert db.add.call_count > 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_passed_to_retriever(self):
        retriever = _mock_retriever()
        service = IngestService(retriever=retriever, db=_mock_db())
        await service.ingest(text=SAMPLE_TEXT, title="Test",
                             jurisdiction="DE", task_category="passport")
        embedded = retriever.add_chunks.call_args[0][0]
        for c in embedded:
            assert c.metadata["jurisdiction"] == "DE"
            assert c.metadata["task_category"] == "passport"

    @pytest.mark.asyncio
    async def test_fallback_to_parents_when_no_children(self):
        retriever = _mock_retriever()
        service = IngestService(retriever=retriever, db=_mock_db())
        # Single short paragraph — no children produced
        await service.ingest(text="Just a single short paragraph with no headings.",
                             title="Tiny")
        retriever.add_chunks.assert_called_once()
        embedded = retriever.add_chunks.call_args[0][0]
        assert len(embedded) >= 1
