"""Performance and scalability tests — high-volume ingestion and retrieval timing."""
import time
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from backend.rag.fusion import RetrievedChunk
from backend.rag.chunker import structured_chunk


SAMPLE_DOCUMENTS = [
    ("Residence Permit Renewal", "Procedure:\nYou need a passport photo, letter of award, and health insurance.\nVisit the Immigration Office within 15 days of arrival.\nBring all original documents plus copies.\n\nRequired documents:\n- Passport-size photo\n- Letter of Award\n- Proof of health insurance\n- Transcript of academic records\n- Proof of accommodation"),
    ("Health Insurance", "Health insurance:\nScholarship holders are entitled to TAJ card coverage.\nThe TAJ card covers all public health services.\nProcessing takes approximately 2-3 weeks.\n\nPrivate insurance:\n- Valid from date of arrival\n- Covers emergency services\n- Required documents: passport, enrollment letter"),
    ("Address Card", "Introduction:\nAll foreign residents must register their accommodation.\nUse the Enter Hungary portal to submit change of address.\nUpload lease agreement and landlord declaration.\n\nProcess:\n- Log in to Enter Hungary\n- Select change of accommodation\n- Upload required documents\n- Wait for confirmation email"),
    ("Tax ID Application", "Introduction:\nScholarship holders need a Hungarian tax ID.\nVisit the central tax office in Budapest.\nBusiness hours: Monday to Friday 8:00-16:00.\n\nRequired:\n- Passport\n- Address card\n- Enrollment certificate"),
    ("Student ID", "Student ID:\nRequest temporary certificate via Neptun E066.\nThe certificate is valid for 60 days.\nPermanent card arrives by post within 30 days.\n\nSteps:\n- Log in to Neptun\n- Submit E066 request\n- Print temporary certificate\n- Collect permanent card from faculty office"),
]


def _make_retriever(docs_count=20):
    """Build a HybridRetriever with mocked embedding model and real BM25."""
    with patch("backend.rag.retriever.SentenceTransformer") as MockST, \
         patch("backend.rag.retriever.chromadb") as mock_chroma:

        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = np.random.randn(1, 384).astype("float32")
        MockST.return_value = mock_encoder

        mock_collection = MagicMock()
        mock_collection.count.return_value = 0

        mock_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}
        mock_collection.query.return_value = {
            "ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]],
        }

        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chroma.PersistentClient.return_value = mock_client

        from backend.rag.retriever import HybridRetriever
        retriever = HybridRetriever()

        # Ingest multiple documents to build BM25 index
        all_chunks = []
        for i in range(docs_count):
            title, text = SAMPLE_DOCUMENTS[i % len(SAMPLE_DOCUMENTS)]
            doc_id = f"doc-{i}"
            chunks = structured_chunk(text, doc_id=doc_id)
            children = [c for c in chunks if c.parent_id is not None]
            to_embed = children or [c for c in chunks if c.parent_id is None]
            for c in to_embed:
                all_chunks.append(RetrievedChunk(
                    id=c.id, content=c.content, doc_id=doc_id,
                    parent_content=c.parent_content, section_title=c.section_title,
                    metadata={"jurisdiction": "HU", "parent_id": c.parent_id or "",
                              "section_title": c.section_title, "chunk_type": c.chunk_type},
                ))

        # Update mock to return all chunks for BM25
        mock_collection.get.return_value = {
            "ids": [c.id for c in all_chunks],
            "documents": [c.content for c in all_chunks],
            "metadatas": [c.metadata for c in all_chunks],
        }
        mock_collection.count.return_value = len(all_chunks)

        # Build BM25 with real data
        retriever._rebuild_bm25()

        # Make dense retrieval return top chunks
        def mock_query(**kwargs):
            n = min(kwargs.get("n_results", 5), len(all_chunks))
            return {
                "ids": [[c.id for c in all_chunks[:n]]],
                "documents": [[c.content for c in all_chunks[:n]]],
                "metadatas": [[c.metadata for c in all_chunks[:n]]],
                "distances": [[0.3] * n],
            }
        mock_collection.query.side_effect = mock_query

        return retriever, len(all_chunks)


class TestHighVolumeIngestion:
    def test_ingest_20_documents_builds_index(self):
        retriever, chunk_count = _make_retriever(docs_count=20)
        assert chunk_count > 50  # 20 docs should produce many chunks
        assert retriever._bm25 is not None

    def test_ingest_50_documents_builds_index(self):
        retriever, chunk_count = _make_retriever(docs_count=50)
        assert chunk_count > 100
        assert retriever._bm25 is not None


class TestRetrievalPerformance:
    def test_query_time_with_20_docs(self):
        retriever, _ = _make_retriever(docs_count=20)
        queries = [
            "What documents do I need for residence permit?",
            "How do I get a TAJ card?",
            "Where is the immigration office?",
            "What is the E066 request?",
            "How do I register my address?",
            "What does health insurance cover?",
            "Where is the tax office?",
            "How long is the student certificate valid?",
            "What are the business hours?",
            "Do I need a passport photo?",
        ]

        times = []
        for q in queries:
            start = time.time()
            dense, bm25 = retriever.retrieve(q, jurisdiction="HU")
            elapsed = time.time() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # Retrieval should complete within reasonable time
        assert avg_time < 2.0, f"Average retrieval too slow: {avg_time:.3f}s"
        assert max_time < 5.0, f"Max retrieval too slow: {max_time:.3f}s"

    def test_query_time_with_50_docs(self):
        retriever, _ = _make_retriever(docs_count=50)
        queries = [
            "residence permit renewal documents",
            "TAJ card application process",
            "address registration Hungary",
            "tax ID requirements",
            "student ID temporary certificate",
        ]

        times = []
        for q in queries:
            start = time.time()
            dense, bm25 = retriever.retrieve(q, jurisdiction="HU")
            elapsed = time.time() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        assert avg_time < 3.0, f"Average retrieval too slow at 50 docs: {avg_time:.3f}s"
        assert max_time < 5.0, f"Max retrieval too slow at 50 docs: {max_time:.3f}s"

    def test_bm25_returns_results_at_scale(self):
        retriever, _ = _make_retriever(docs_count=20)
        results = retriever._bm25_retrieve("passport photo residence", 10, "HU")
        assert len(results) > 0

    def test_no_errors_under_repeated_queries(self):
        retriever, _ = _make_retriever(docs_count=20)
        errors = 0
        for i in range(50):
            try:
                retriever.retrieve(f"query number {i}", jurisdiction="HU")
            except Exception:
                errors += 1
        assert errors == 0, f"{errors} errors in 50 queries"


class TestBm25RebuildScaling:
    def test_rebuild_time_20_docs(self):
        retriever, chunk_count = _make_retriever(docs_count=20)
        start = time.time()
        retriever._rebuild_bm25()
        elapsed = time.time() - start
        assert elapsed < 2.0, f"BM25 rebuild too slow for 20 docs: {elapsed:.3f}s"

    def test_rebuild_time_50_docs(self):
        retriever, chunk_count = _make_retriever(docs_count=50)
        start = time.time()
        retriever._rebuild_bm25()
        elapsed = time.time() - start
        assert elapsed < 5.0, f"BM25 rebuild too slow for 50 docs: {elapsed:.3f}s"
