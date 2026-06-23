"""Structured document chunker: splits text into parent sections and child paragraphs/list items."""

import re
import uuid
import logging
from dataclasses import dataclass, field

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class StructuredChunk:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    parent_content: str = ""
    section_title: str = ""
    chunk_type: str = "section"  # "section" (parent) | "paragraph" | "list_item"
    doc_id: str = ""
    parent_id: str | None = None


# Detect section headings: colon-terminated lines or short all-caps lines
def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.endswith(":") and len(stripped) < 100:
        return True
    if stripped.isupper() and len(stripped.split()) <= 10:
        return True
    return False


# Detect list items: lines starting with -, *, bullet, or numbered patterns
def _is_list_item(line: str) -> bool:
    stripped = line.strip()
    return bool(
        re.match(r"^[\-\*\u2022]\s+", stripped)
        or re.match(r"^\d+[.\)]\s+", stripped)
    )


def _word_count(text: str) -> int:
    return len(text.split())


# Split oversized text into fixed-size chunks with overlap
def _fallback_split(text: str, doc_id: str, section_title: str,
                    parent_id: str, parent_content: str) -> list[StructuredChunk]:
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        end = start + settings.chunk_size
        chunk_text = " ".join(words[start:end])
        if chunk_text.strip():
            chunks.append(StructuredChunk(
                content=chunk_text, parent_content=parent_content,
                section_title=section_title, chunk_type="paragraph",
                doc_id=doc_id, parent_id=parent_id,
            ))
        start += settings.chunk_size - settings.chunk_overlap
    return chunks


# Break a section's body into paragraph and list-item children
def _split_section_into_children(
    section_text: str, section_title: str, doc_id: str,
    parent_id: str, parent_content: str,
) -> list[StructuredChunk]:
    lines = section_text.split("\n")
    children: list[StructuredChunk] = []
    current_paragraph: list[str] = []

    def flush():
        nonlocal current_paragraph
        if current_paragraph:
            text = "\n".join(current_paragraph).strip()
            if text:
                children.append(StructuredChunk(
                    content=text, parent_content=parent_content,
                    section_title=section_title, chunk_type="paragraph",
                    doc_id=doc_id, parent_id=parent_id,
                ))
            current_paragraph = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
        elif _is_list_item(stripped):
            flush()
            children.append(StructuredChunk(
                content=stripped, parent_content=parent_content,
                section_title=section_title, chunk_type="list_item",
                doc_id=doc_id, parent_id=parent_id,
            ))
        else:
            current_paragraph.append(stripped)

    flush()
    return children


# Main entry point: split document by headings into parent sections, then split each into children
def structured_chunk(text: str, doc_id: str) -> list[StructuredChunk]:
    """Split a document into structured parent-child chunks."""
    lines = text.split("\n")
    sections: list[tuple[str, list[str]]] = []
    current_title = "Introduction"
    current_lines: list[str] = []

    for line in lines:
        if _is_heading(line):
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = line.strip().rstrip(":")
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))

    all_chunks: list[StructuredChunk] = []

    for title, section_lines in sections:
        section_text = "\n".join(section_lines).strip()
        if not section_text:
            continue

        parent = StructuredChunk(
            content=section_text, parent_content=section_text,
            section_title=title, chunk_type="section",
            doc_id=doc_id, parent_id=None,
        )
        all_chunks.append(parent)

        children = _split_section_into_children(
            section_text, title, doc_id, parent.id, section_text,
        )

        if not children:
            parent.chunk_type = "paragraph"
            continue

        final_children = []
        for child in children:
            if _word_count(child.content) > settings.chunk_size:
                final_children.extend(_fallback_split(
                    child.content, doc_id, title, parent.id, section_text,
                ))
            else:
                final_children.append(child)

        all_chunks.extend(final_children)

    parents = [c for c in all_chunks if c.parent_id is None]
    children = [c for c in all_chunks if c.parent_id is not None]
    logger.info(
        f"Structured chunking: {len(sections)} sections -> "
        f"{len(parents)} parents, {len(children)} children"
    )
    return all_chunks
