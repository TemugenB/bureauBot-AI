from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

from backend.rag.fusion import RetrievedChunk

logger = logging.getLogger(__name__)

_CITATION_PATTERN = re.compile(r"\[SRC:([a-zA-Z0-9\-_]+)\]")


@dataclass
class Citation:
    chunk_id: str
    doc_id: str
    score: float
    excerpt: str = ""


@dataclass
class VerificationResult:
    verified: bool
    citations: list[Citation] = field(default_factory=list)
    ungrounded_sentences: list[str] = field(default_factory=list)
    clean_response: str = ""


class CitationVerifier:

    def verify(
        self, response: str, source_chunks: list[RetrievedChunk],
    ) -> VerificationResult:
        chunk_map = {c.id: c for c in source_chunks}

        cited_ids = set(_CITATION_PATTERN.findall(response))
        citations: list[Citation] = []
        for cid in cited_ids:
            if cid in chunk_map:
                chunk = chunk_map[cid]
                citations.append(Citation(
                    chunk_id=cid, doc_id=chunk.doc_id, score=chunk.score,
                    excerpt=chunk.content[:120] + "…" if len(chunk.content) > 120 else chunk.content,
                ))
            else:
                logger.warning(f"Verifier: cited chunk_id '{cid}' not in source set.")

        ungrounded = self._find_ungrounded(response)
        clean = _CITATION_PATTERN.sub("", response).strip()
        verified = len(ungrounded) == 0

        if not verified:
            logger.warning(f"Verifier flagged {len(ungrounded)} potentially ungrounded sentence(s).")

        return VerificationResult(
            verified=verified, citations=citations,
            ungrounded_sentences=ungrounded, clean_response=clean,
        )

    def _find_ungrounded(self, response: str) -> list[str]:
        factual_keywords = re.compile(
            r"\b(must|required|need|valid|days|weeks|months|fee|cost|form|"
            r"document|apply|submit|official|law|regulation|deadline|€|\d+)\b",
            re.IGNORECASE,
        )
        sentences = re.split(r"(?<=[.!?])\s+", response)
        return [
            s.strip() for s in sentences
            if factual_keywords.search(s) and not _CITATION_PATTERN.search(s)
        ]

    @staticmethod
    def build_system_prompt(source_chunks: list[RetrievedChunk]) -> str:
        blocks = []
        for i, c in enumerate(source_chunks):
            content = c.parent_content if c.parent_content else c.content
            block = f"[SOURCE {i+1} | id:{c.id} | section:{c.section_title}]\n{content}"
            if c.child_content and c.child_content != content:
                block += f"\n\n>>> MOST RELEVANT SECTION:\n{c.child_content}"
            blocks.append(block)

        context_block = "\n\n".join(blocks)

        return f"""You are an official administrative assistant that helps users \
navigate government procedures such as passport renewal, document applications, \
and other administrative tasks.

STRICT RULES — you MUST follow all of these:
1. Answer ONLY using information from the SOURCE BLOCKS below.
2. After EVERY factual claim, append a citation marker in the format [SRC:chunk_id].
3. If the answer is not found in the sources, reply exactly:
   "I cannot find this information in the official documents provided."
4. Do NOT add, invent, or infer any information not present in the sources.
5. Be clear, structured, and helpful. Use bullet points for multi-step processes.
6. Pay special attention to the >>> MOST RELEVANT SECTION markers.

--- OFFICIAL SOURCE DOCUMENTS ---
{context_block}
--- END OF SOURCES ---

Now answer the user's question using only the above sources, with [SRC:id] citations."""
