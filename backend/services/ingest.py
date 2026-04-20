from __future__ import annotations

import asyncio
import argparse
import uuid
import logging
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.models import Document, DocumentChunk
from backend.rag.chunker import structured_chunk, StructuredChunk
from backend.rag.retriever import HybridRetriever
from backend.rag.fusion import RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()

_CATEGORY_HINTS: dict[str, str] = {
    "passport": "passport", "utlevel": "passport",
    "birth": "birth_certificate", "szuletesi": "birth_certificate",
    "driving": "driving_licence", "jogositvany": "driving_licence",
    "residence": "residence_permit", "letelepedes": "residence_permit",
    "marriage": "marriage_certificate", "hazassag": "marriage_certificate",
    "tax": "tax", "ado": "tax",
}


def _guess_category(filename: str) -> str | None:
    name_lower = filename.lower()
    for keyword, category in _CATEGORY_HINTS.items():
        if keyword in name_lower:
            return category
    return None


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
        # Upsert: remove existing document with same title+jurisdiction
        from sqlalchemy import select, delete
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

        # Embed children into ChromaDB; fall back to parents if no children
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


# ---------------------------------------------------------------------------
# CLI: python -m backend.services.ingest --dir ./corpus
# ---------------------------------------------------------------------------

async def _ingest_file(path: Path, title: str | None, jurisdiction: str,
                       category: str | None, retriever: HybridRetriever) -> None:
    text = _read_file(path)
    if not text.strip():
        logger.warning(f"Skipping empty file: {path.name}")
        return
    doc_title = title or path.stem.replace("_", " ").replace("-", " ").title()
    doc_category = category or _guess_category(path.name)
    from backend.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        service = IngestService(retriever=retriever, db=db)
        doc_id = await service.ingest(text=text, title=doc_title,
                                      jurisdiction=jurisdiction,
                                      task_category=doc_category,
                                      source_url=str(path))
    logger.info(f"✓ Ingested '{doc_title}' → doc_id={doc_id}")


async def _cli_main(args: argparse.Namespace) -> None:
    from backend.db.session import init_db
    await init_db()
    retriever = HybridRetriever()

    if args.file:
        path = Path(args.file)
        if not path.exists():
            logger.error(f"File not found: {path}")
            sys.exit(1)
        await _ingest_file(path, args.title, args.jurisdiction, args.category, retriever)
    elif args.dir:
        corpus_dir = Path(args.dir)
        if not corpus_dir.is_dir():
            logger.error(f"Directory not found: {corpus_dir}")
            sys.exit(1)
        files = sorted(
            list(corpus_dir.glob("**/*.txt")) +
            list(corpus_dir.glob("**/*.md")) +
            list(corpus_dir.glob("**/*.pdf"))
        )
        if not files:
            logger.warning(f"No supported files found in {corpus_dir}")
            return
        logger.info(f"Found {len(files)} file(s) in {corpus_dir}")
        for p in files:
            await _ingest_file(p, None, args.jurisdiction, None, retriever)
    else:
        logger.error("Provide --file or --dir")
        sys.exit(1)
    logger.info("Corpus ingestion complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    parser = argparse.ArgumentParser(description="Ingest documents into the Admin Assistant corpus.")
    parser.add_argument("--file", help="Path to a single document file")
    parser.add_argument("--dir", help="Path to a directory of documents")
    parser.add_argument("--title", help="Document title (single file only)")
    parser.add_argument("--jurisdiction", default="HU", help="ISO country code (default: HU)")
    parser.add_argument("--category", help="Task category override (single file only)")
    asyncio.run(_cli_main(parser.parse_args()))
