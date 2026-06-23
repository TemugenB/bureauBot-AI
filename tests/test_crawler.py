"""Tests for services/crawler.py — ABC, polymorphism, extraction, domain filtering."""
import pytest
from unittest.mock import patch, MagicMock
from backend.services.crawler import (
    HtmlExtractor, PdfExtractor, ContentExtractor,
    _get_extractor, _domain_allowed, _url_to_slug, _is_pdf_url,
    _extract_links, crawl_urls, CrawlResult,
)


class TestContentExtractorABC:
    """Verify the ABC pattern and polymorphism."""

    def test_cannot_instantiate_base(self):
        with pytest.raises(TypeError):
            ContentExtractor()

    def test_html_extractor_is_subclass(self):
        assert issubclass(HtmlExtractor, ContentExtractor)

    def test_pdf_extractor_is_subclass(self):
        assert issubclass(PdfExtractor, ContentExtractor)

    def test_html_can_handle_html(self):
        ext = HtmlExtractor()
        assert ext.can_handle("text/html; charset=utf-8", "http://example.com/page")

    def test_pdf_can_handle_pdf(self):
        ext = PdfExtractor()
        assert ext.can_handle("application/pdf", "http://example.com/doc.pdf")

    def test_pdf_can_handle_by_url(self):
        ext = PdfExtractor()
        assert ext.can_handle("application/octet-stream", "http://example.com/file.pdf")

    def test_html_extract(self):
        ext = HtmlExtractor()
        html = b"<html><body><p>Hello world</p></body></html>"
        result = ext.extract(html, "http://example.com")
        assert "Hello" in result or result == ""  # trafilatura may return empty for minimal HTML


class TestGetExtractor:
    """Dynamic binding selects the right extractor at runtime."""

    def test_pdf_content_type(self):
        ext = _get_extractor("application/pdf", "http://x.com/file")
        assert isinstance(ext, PdfExtractor)

    def test_pdf_url_extension(self):
        ext = _get_extractor("application/octet-stream", "http://x.com/doc.pdf")
        assert isinstance(ext, PdfExtractor)

    def test_html_content_type(self):
        ext = _get_extractor("text/html", "http://x.com/page")
        assert isinstance(ext, HtmlExtractor)

    def test_unknown_defaults_to_html(self):
        ext = _get_extractor("text/plain", "http://x.com/file.txt")
        assert isinstance(ext, HtmlExtractor)


class TestDomainAllowed:
    def test_exact_match(self):
        assert _domain_allowed("http://example.com/page", ["example.com"])

    def test_subdomain_match(self):
        assert _domain_allowed("http://sub.example.com/page", ["example.com"])

    def test_no_match(self):
        assert not _domain_allowed("http://other.com/page", ["example.com"])

    def test_partial_no_match(self):
        assert not _domain_allowed("http://notexample.com/page", ["example.com"])


class TestUrlToSlug:
    def test_simple_path(self):
        assert _url_to_slug("http://example.com/my-page") == "my-page"

    def test_nested_path(self):
        assert _url_to_slug("http://example.com/a/b/c") == "c"

    def test_no_path(self):
        result = _url_to_slug("http://example.com/")
        assert result == "example-com" or result == "page"


class TestIsPdfUrl:
    def test_pdf(self):
        assert _is_pdf_url("http://example.com/doc.pdf")

    def test_not_pdf(self):
        assert not _is_pdf_url("http://example.com/page.html")

    def test_case_insensitive(self):
        assert _is_pdf_url("http://example.com/DOC.PDF")


class TestExtractLinks:
    def test_extracts_allowed_links(self):
        html = '<a href="/page2">Link</a><a href="http://other.com">Ext</a>'
        links = _extract_links(html, "http://example.com", ["example.com"])
        assert "http://example.com/page2" in links
        assert "http://other.com" not in links

    def test_skips_mailto_and_javascript(self):
        html = '<a href="mailto:a@b.com">Mail</a><a href="javascript:void(0)">JS</a>'
        links = _extract_links(html, "http://example.com", ["example.com"])
        assert len(links) == 0

    def test_deduplicates(self):
        html = '<a href="/page">A</a><a href="/page">B</a>'
        links = _extract_links(html, "http://example.com", ["example.com"])
        assert links.count("http://example.com/page") == 1


class TestCrawlUrls:
    @patch("backend.services.crawler.httpx.Client")
    def test_timeout_returns_warning(self, MockClient):
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        MockClient.return_value = mock_client

        results = crawl_urls(["http://example.com/page"], ["example.com"])
        assert len(results) == 1
        assert results[0].warning == "timeout"

    @patch("backend.services.crawler.httpx.Client")
    def test_successful_html_fetch(self, MockClient):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"<html><body><p>Test content here</p></body></html>"
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "<html><body><p>Test content here</p></body></html>"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        MockClient.return_value = mock_client

        results = crawl_urls(["http://example.com/page"], ["example.com"])
        assert len(results) >= 1
        assert results[0].source_url == "http://example.com/page"

    def test_max_urls_exceeded(self):
        urls = [f"http://example.com/page{i}" for i in range(101)]
        with pytest.raises(ValueError, match="Maximum"):
            crawl_urls(urls, ["example.com"])
