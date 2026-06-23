"""Multi-query translator: expands a user question into alternative phrasings via the LLM."""

import logging
import re
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_MULTI_QUERY_PROMPT = """\
You are an expert at reformulating search queries for an administrative \
document retrieval system.

Given the user's question below, generate {n} alternative versions of it \
that would help retrieve relevant official administrative information. \
Each version should approach the question from a different angle or use \
different terminology (synonyms, official jargon, procedural framing).

Output ONLY the alternative questions, one per line, with no numbering, \
bullets, or extra text.

User question: {question}
"""


class MultiQueryTranslator:


    def __init__(self, llm_fn, n: int | None = None):
        self.llm_fn = llm_fn
        self.n = n or settings.multi_query_count

    async def translate(self, question: str) -> list[str]:
        prompt = _MULTI_QUERY_PROMPT.format(n=self.n, question=question)

        try:
            raw = await self.llm_fn(prompt)
            variants = self._parse_variants(raw)
        except Exception as exc:
            logger.warning(f"Multi-query generation failed: {exc}. Falling back to original.")
            variants = []

        all_queries = [question] + [v for v in variants if v.lower() != question.lower()]
        all_queries = all_queries[: self.n + 1]

        logger.debug(f"Multi-query expanded to {len(all_queries)} queries: {all_queries}")
        return all_queries


    def _parse_variants(self, raw: str) -> list[str]:
        lines = raw.strip().splitlines()
        variants = []
        for line in lines:
            cleaned = re.sub(r"^[\s\-\d\.\)]+", "", line).strip()
            if cleaned and len(cleaned) > 10:
                variants.append(cleaned)
        return variants[: self.n]
