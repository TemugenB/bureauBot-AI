"""Tests for rag/retriever.py — mock ChromaDB and SentenceTransformer."""
import numpy as np
from unittest.mock import patch, MagicMock
from backend.rag.fusion import RetrievedChunk


def _make_retriever(collection_docs=None):
    """Build a HybridRetriever with mocked embedding model and ChromaDB."""
    with patch("backend.rag.retriever.SentenceTransformer") as MockST, \
         patch("backend.rag.retriever.chromadb") as mock_chroma:

        # Mock embedding model
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = np.random.randn(1, 384).astype("float32")
        MockST.return_value = mock_encoder

        # Mock ChromaDB collection
        mock_collection = MagicMock()
        mock_collection.count.return_value = len(collection_docs or [])

        get_result = {
            "ids": [d["id"] for d in (collection_docs or [])],
            "documents": [d["content"] for d in (collection_docs or [])],
            "metadatas": [d.get("meta", {}) for d in (collection_docs or [])],
        }
        mock_collection.get.return_value = get_result

        mock_collection.query.return_value = {
            "ids": [[d["id"] for d in (collection_docs or [])]],
            "documents": [[d["content"] for d in (collection_docs or [])]],
            "metadatas": [[d.get("meta", {}) for d in (collection_docs or [])]],
            "distances": [[0.2] * len(collection_docs or [])],
        }

        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chroma.PersistentClient.return_value = mock_client

        from backend.rag.retriever import HybridRetriever
        retriever = HybridRetriever()
        return retriever, mock_collection, mock_encoder


class TestAddChunks:
    def test_upserts_to_collection(self):
        retriever, collection, _ = _make_retriever()
        chunks = [RetrievedChunk(id="c1", content="test", doc_id="d1",
                                 metadata={"jurisdiction": "HU", "parent_id": ""})]
        retriever.add_chunks(chunks)
        collection.upsert.assert_called_once()
        call_kwargs = collection.upsert.call_args
        assert call_kwargs[1]["ids"] == ["c1"]

    def test_populates_parent_cache(self):
        retriever, collection, _ = _make_retriever()
        chunks = [RetrievedChunk(id="c1", content="child", doc_id="d1",
                                 parent_content="parent text",
                                 metadata={"parent_id": "p1", "jurisdiction": "HU"})]
        retriever.add_chunks(chunks)
        assert "p1" in retriever._parent_cache

    def test_empty_chunks_noop(self):
        retriever, collection, _ = _make_retriever()
        retriever.add_chunks([])
        collection.upsert.assert_not_called()


class TestRetrieve:
    def test_returns_dense_and_bm25(self):
        docs = [{"id": "c1", "content": "passport renewal info",
                 "meta": {"doc_id": "d1", "jurisdiction": "HU", "section_title": "Proc"}}]
        retriever, _, encoder = _make_retriever(docs)
        encoder.encode.return_value = np.random.randn(1, 384).astype("float32")
        dense, bm25 = retriever.retrieve("passport", jurisdiction="HU")
        assert len(dense) > 0

    def test_jurisdiction_filter_passed(self):
        docs = [{"id": "c1", "content": "test",
                 "meta": {"doc_id": "d1", "jurisdiction": "HU", "section_title": ""}}]
        retriever, collection, _ = _make_retriever(docs)
        retriever.retrieve("query", jurisdiction="HU")
        call_kwargs = collection.query.call_args[1]
        assert call_kwargs.get("where") == {"jurisdiction": "HU"}


class TestAttachParent:
    def test_enriches_with_parent_content(self):
        retriever, _, _ = _make_retriever()
        retriever._parent_cache["p1"] = ("parent text", "Section A")
        chunk = RetrievedChunk(id="c1", content="child", doc_id="d1",
                               metadata={"parent_id": "p1"})
        result = retriever._attach_parent(chunk)
        assert result.parent_content == "parent text"
        assert result.section_title == "Section A"
        assert result.child_content == "child"

    def test_no_parent_unchanged(self):
        retriever, _, _ = _make_retriever()
        chunk = RetrievedChunk(id="c1", content="text", doc_id="d1",
                               metadata={"parent_id": ""})
        result = retriever._attach_parent(chunk)
        assert result.parent_content == ""


class TestBm25Retrieve:
    def test_empty_when_not_built(self):
        retriever, _, _ = _make_retriever()
        result = retriever._bm25_retrieve("query", 10, None)
        assert result == []


class TestEmbed:
    def test_normalizes_vectors(self):
        retriever, _, encoder = _make_retriever()
        raw = np.array([[3.0, 4.0, 0.0]])
        encoder.encode.return_value = raw
        result = retriever.embed(["test"])
        norm = np.linalg.norm(result[0])
        assert abs(norm - 1.0) < 1e-6
