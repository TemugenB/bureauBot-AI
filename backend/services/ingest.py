"""Document ingestion service: chunks text, embeds it, and stores in both databases."""

import uuid
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from backend.config import get_settings
from backend.db.models import Document, DocumentChunk
from backend.rag.chunker import structured_chunk, StructuredChunk
from backend.rag.retriever import HybridRetriever
from backend.rag.fusion import RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()

DEMO_FILES = {
    "residence_renewal.txt": {"title": "Residence Renewal", "category": "residence_permit"},
    "health_insurance.txt": {"title": "Health Insurance", "category": "health_insurance"},
    "address_card.txt": {"title": "Address Card", "category": "address_card"},
}


def _read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        try:
            from pdfminer.high_level import extract_text
            return extract_text(str(path))
        except ImportError:
            logger.error("PDF support requires: pip install pdfminer.six")
            return ""
    logger.warning(f"Unsupported file type: {suffix} — skipping {path.name}")
    return ""


class IngestService:

    def __init__(self, retriever: HybridRetriever, db: AsyncSession):
        self.retriever = retriever
        self.db = db

    async def ingest(
        self, text: str, title: str, jurisdiction: str = "HU",
        task_category: Optional[str] = None, source_url: Optional[str] = None,
    ) -> str:
        # Replace existing document with same title+jurisdiction if it exists
        existing = await self.db.execute(
            select(Document).where(Document.title == title, Document.jurisdiction == jurisdiction)
        )
        old_doc = existing.scalar()
        if old_doc:
            await self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == old_doc.id))
            await self.db.execute(delete(Document).where(Document.id == old_doc.id))
            logger.info(f"Replaced existing document '{title}' [{old_doc.id}]")

        doc_id = str(uuid.uuid4())
        logger.info(f"Ingesting document '{title}' [{doc_id}]")

        chunks = structured_chunk(text, doc_id=doc_id)
        children = [c for c in chunks if c.parent_id is not None]

        # Embed children if available, otherwise fall back to parent chunks
        to_embed = children or [c for c in chunks if c.parent_id is None]
        self.retriever.add_chunks([
            RetrievedChunk(
                id=c.id, content=c.content, doc_id=doc_id,
                parent_content=c.parent_content, section_title=c.section_title,
                metadata={
                    "jurisdiction": jurisdiction,
                    "task_category": task_category or "",
                    "parent_id": c.parent_id or "",
                    "section_title": c.section_title,
                    "chunk_type": c.chunk_type,
                },
            )
            for c in to_embed
        ])

        await self._persist(doc_id, title, source_url, jurisdiction, task_category, chunks)
        return doc_id

    async def _persist(
        self, doc_id: str, title: str, source_url: Optional[str],
        jurisdiction: str, task_category: Optional[str],
        chunks: list[StructuredChunk],
    ) -> None:
        self.db.add(Document(
            id=doc_id, title=title, source_url=source_url,
            jurisdiction=jurisdiction, task_category=task_category,
            chunk_count=len(chunks),
        ))
        for c in chunks:
            self.db.add(DocumentChunk(
                id=c.id, document_id=doc_id, parent_id=c.parent_id,
                content=c.content, section_title=c.section_title,
                chunk_type=c.chunk_type, token_count=len(c.content.split()),
                meta={"doc_id": doc_id},
            ))
        await self.db.commit()
        logger.info(f"  Persisted {len(chunks)} chunks to PostgreSQL.")


async def load_demo_data(retriever: HybridRetriever, db: AsyncSession) -> list[str]:
    corpus_dir = Path(__file__).resolve().parent.parent.parent / "corpus"
    service = IngestService(retriever=retriever, db=db)
    doc_ids = []
    for filename, meta in DEMO_FILES.items():
        path = corpus_dir / filename
        if not path.exists():
            logger.warning(f"Demo file not found: {path}")
            continue
        text = _read_file(path)
        if not text.strip():
            continue
        doc_id = await service.ingest(
            text=text, title=meta["title"],
            jurisdiction="HU", task_category=meta["category"],
        )
        doc_ids.append(doc_id)
        logger.info(f"✓ Demo ingested '{meta['title']}' → {doc_id}")
    return doc_ids
