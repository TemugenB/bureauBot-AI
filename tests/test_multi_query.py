"""Tests for rag/multi_query.py — mock LLM."""
import pytest
from unittest.mock import AsyncMock
from backend.rag.multi_query import MultiQueryTranslator


@pytest.fixture
def mock_llm():
    fn = AsyncMock(return_value="How to renew residence permit?\nResidence permit extension process?")
    return fn


class TestMultiQueryTranslator:
    @pytest.mark.asyncio
    async def test_returns_original_plus_variants(self, mock_llm):
        t = MultiQueryTranslator(llm_fn=mock_llm, n=2)
        result = await t.translate("renew my permit")
        assert result[0] == "renew my permit"
        assert len(result) == 3  # original + 2 variants

    @pytest.mark.asyncio
    async def test_deduplicates_case_insensitive(self, mock_llm):
        mock_llm.return_value = "Renew My Permit\nAnother variant?"
        t = MultiQueryTranslator(llm_fn=mock_llm, n=2)
        result = await t.translate("renew my permit")
        # "Renew My Permit" matches original case-insensitively, should be dropped
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self):
        failing_llm = AsyncMock(side_effect=Exception("API down"))
        t = MultiQueryTranslator(llm_fn=failing_llm, n=3)
        result = await t.translate("my question")
        assert result == ["my question"]

    @pytest.mark.asyncio
    async def test_respects_n_limit(self, mock_llm):
        mock_llm.return_value = "V1?\nV2?\nV3?\nV4?\nV5?"
        t = MultiQueryTranslator(llm_fn=mock_llm, n=2)
        result = await t.translate("original")
        assert len(result) <= 3  # original + n

    @pytest.mark.asyncio
    async def test_deterministic_parsing(self, mock_llm):
        mock_llm.return_value = "1. First variant\n2. Second variant"
        t = MultiQueryTranslator(llm_fn=mock_llm, n=2)
        r1 = await t.translate("test")
        r2 = await t.translate("test")
        assert r1 == r2


class TestParseVariants:
    def test_strips_numbering(self):
        t = MultiQueryTranslator(llm_fn=AsyncMock(), n=3)
        result = t._parse_variants("1. First question here?\n2. Second question here?")
        assert not any(v.startswith("1.") for v in result)

    def test_strips_bullets(self):
        t = MultiQueryTranslator(llm_fn=AsyncMock(), n=3)
        result = t._parse_variants("- First question here?\n- Second question here?")
        assert not any(v.startswith("-") for v in result)

    def test_filters_short_lines(self):
        t = MultiQueryTranslator(llm_fn=AsyncMock(), n=3)
        result = t._parse_variants("OK\nThis is a proper question variant?")
        assert len(result) == 1  # "OK" is too short (<=10 chars)
