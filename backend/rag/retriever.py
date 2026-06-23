"""Hybrid retriever combining dense vector search (ChromaDB) with sparse keyword search (BM25)."""

import logging
from typing import Optional

import chromadb
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from backend.config import get_settings
from backend.rag.fusion import RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()


class HybridRetriever:

    def __init__(self):
        self._embedder = SentenceTransformer(settings.embedding_model)
        self._chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._chroma_client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_chunks: list[RetrievedChunk] = []
        self._parent_cache: dict[str, tuple[str, str]] = {}

    # Encode texts into normalised unit vectors for cosine similarity search
    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._embedder.encode(texts, batch_size=32, show_progress_bar=False)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / (norms + 1e-9)

    # Index chunks into both ChromaDB (vectors) and BM25 (keywords), then cache parent content
    def add_chunks(self, chunks: list[RetrievedChunk]) -> None:
        if not chunks:
            return

        texts = [c.content for c in chunks]
        embeddings = self.embed(texts).tolist()
        ids = [c.id for c in chunks]
        metadatas = [
            {
                "doc_id": c.doc_id,
                "section_title": c.section_title,
                "parent_id": c.metadata.get("parent_id", ""),
                **{k: str(v) for k, v in c.metadata.items()},
            }
            for c in chunks
        ]

        self._collection.upsert(
            ids=ids, documents=texts,
            embeddings=embeddings, metadatas=metadatas,
        )

        for c in chunks:
            pid = c.metadata.get("parent_id", "")
            if pid and c.parent_content:
                self._parent_cache[pid] = (c.parent_content, c.section_title)

        self._rebuild_bm25()
        logger.info(f"Indexed {len(chunks)} chunks into Chroma + BM25.")

    # Reload all chunks from ChromaDB and rebuild the BM25 index from scratch
    def _rebuild_bm25(self) -> None:
        result = self._collection.get(include=["documents", "metadatas"])
        self._bm25_chunks = [
            RetrievedChunk(
                id=cid, content=doc, doc_id=meta.get("doc_id", ""),
                section_title=meta.get("section_title", ""), metadata=meta,
            )
            for cid, doc, meta in zip(
                result["ids"], result["documents"], result["metadatas"]
            )
        ]
        tokenised = [c.content.lower().split() for c in self._bm25_chunks]
        self._bm25 = BM25Okapi(tokenised) if tokenised else None

    def retrieve(
        self, query: str, top_k: int | None = None,
        jurisdiction: str | None = None,
    ) -> tuple[list[RetrievedChunk], list[RetrievedChunk]]:
        top_k = top_k or settings.retrieval_top_k
        where_filter = {"jurisdiction": jurisdiction} if jurisdiction else None

        dense = self._dense_retrieve(query, top_k, where_filter)
        bm25 = self._bm25_retrieve(query, top_k, jurisdiction)

        dense = [self._attach_parent(c) for c in dense]
        bm25 = [self._attach_parent(c) for c in bm25]
        return dense, bm25

    # Enrich a child chunk with its parent's content for broader LLM context
    def _attach_parent(self, chunk: RetrievedChunk) -> RetrievedChunk:
        pid = chunk.metadata.get("parent_id", "")
        if pid and pid in self._parent_cache:
            parent_content, section_title = self._parent_cache[pid]
            chunk.parent_content = parent_content
            chunk.child_content = chunk.content
            chunk.section_title = section_title
        return chunk

    # Query ChromaDB with the embedded query vector; convert cosine distance to similarity score
    def _dense_retrieve(self, query: str, top_k: int,
                        where_filter: dict | None) -> list[RetrievedChunk]:
        query_vec = self.embed([query])[0].tolist()
        kwargs = {
            "query_embeddings": [query_vec],
            "n_results": min(top_k, self._collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if where_filter:
            kwargs["where"] = where_filter

        result = self._collection.query(**kwargs)
        chunks = []
        for cid, doc, meta, dist in zip(
            result["ids"][0], result["documents"][0],
            result["metadatas"][0], result["distances"][0],
        ):
            chunks.append(RetrievedChunk(
                id=cid, content=doc, doc_id=meta.get("doc_id", ""),
                section_title=meta.get("section_title", ""),
                score=1.0 - float(dist), metadata=meta,
            ))
        return chunks

    # Score all chunks by keyword overlap, filter by jurisdiction, return top-k
    def _bm25_retrieve(self, query: str, top_k: int,
                       jurisdiction: str | None) -> list[RetrievedChunk]:
        if not self._bm25 or not self._bm25_chunks:
            return []

        scores = self._bm25.get_scores(query.lower().split())
        filtered = [
            (i, s) for i, (c, s) in enumerate(zip(self._bm25_chunks, scores))
            if jurisdiction is None or c.metadata.get("jurisdiction") == jurisdiction
        ]
        filtered.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in filtered[:top_k]:
            chunk = self._bm25_chunks[idx]
            chunk.bm25_score = float(score)
            results.append(chunk)
        return results
