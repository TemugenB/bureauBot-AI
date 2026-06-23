"""Web crawler: fetches URLs, extracts text from HTML/PDF using polymorphic extractors, and follows links."""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from pdfminer.high_level import extract_text as pdf_extract_text

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0
_MAX_SIZE = 10 * 1024 * 1024  # 10MB
_MAX_URLS = 100


@dataclass
class CrawlResult:
    filename: str
    source_url: str
    content: str
    is_pdf: bool = False
    warning: str | None = None


# Content Extractors (ABC + polymorphism + overriding)

class ContentExtractor(ABC):
    """Base extractor — subclasses override extract() for different content types."""

    @abstractmethod
    def can_handle(self, content_type: str, url: str) -> bool: ...

    @abstractmethod
    def extract(self, raw: bytes, url: str) -> str: ...


class HtmlExtractor(ContentExtractor):
    """Extracts text from HTML pages using trafilatura."""

    def can_handle(self, content_type: str, url: str) -> bool:
        return "text/html" in content_type or not _is_pdf_url(url)

    def extract(self, raw: bytes, url: str) -> str:
        return trafilatura.extract(raw.decode(errors="replace")) or ""


class PdfExtractor(ContentExtractor):
    """Extracts text from PDF documents using pdfminer."""

    def can_handle(self, content_type: str, url: str) -> bool:
        return "application/pdf" in content_type or _is_pdf_url(url)

    def extract(self, raw: bytes, url: str) -> str:
        return pdf_extract_text(BytesIO(raw)).strip()


# Registry — dynamic binding selects the right extractor at runtime
_EXTRACTORS: list[ContentExtractor] = [PdfExtractor(), HtmlExtractor()]


def _get_extractor(content_type: str, url: str) -> ContentExtractor:
    for ext in _EXTRACTORS:
        if ext.can_handle(content_type, url):
            return ext
    return HtmlExtractor()


# Helpers

def _url_to_slug(url: str) -> str:
    path = urlparse(url).path.strip("/")
    slug = path.split("/")[-1] if path else urlparse(url).netloc
    slug = re.sub(r"[^a-zA-Z0-9\-_]", "-", slug).strip("-")
    return slug or "page"


def _is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _domain_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


def _extract_links(html: str, base_url: str, allowed_domains: list[str]) -> list[str]:
    links = []
    for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        href = match.group(1)
        if href.startswith(("#", "mailto:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        if _domain_allowed(absolute, allowed_domains):
            links.append(absolute)
    return list(dict.fromkeys(links))


# Main crawl function

def crawl_urls(urls: list[str], allowed_domains: list[str]) -> list[CrawlResult]:
    if len(urls) > _MAX_URLS:
        raise ValueError(f"Maximum {_MAX_URLS} URLs allowed per crawl")

    allowed_domains = [d.lower() for d in allowed_domains]
    results: list[CrawlResult] = []
    seen_urls: set[str] = set()

    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            parent_slug = _url_to_slug(url)
            result = _fetch_single(client, url, parent_slug)
            if result:
                results.append(result)

            if not result or result.is_pdf:
                continue
            try:
                resp = client.get(url)
                main_content = trafilatura.extract(resp.text, include_links=True, output_format="html") or ""
                child_links = _extract_links(main_content, url, allowed_domains)
            except Exception:
                child_links = []

            for child_url in child_links[:10]:
                if child_url in seen_urls:
                    continue
                seen_urls.add(child_url)
                child_slug = _url_to_slug(child_url)
                filename = f"{parent_slug}-{child_slug}"
                child_result = _fetch_single(client, child_url, filename)
                if child_result:
                    results.append(child_result)

    return results


def _fetch_single(client: httpx.Client, url: str, slug: str) -> CrawlResult | None:
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except httpx.TimeoutException:
        logger.warning(f"Timeout fetching {url}")
        return CrawlResult(filename=f"{slug}.txt", source_url=url, content="", warning="timeout")
    except httpx.HTTPError as exc:
        logger.warning(f"HTTP error fetching {url}: {exc}")
        return CrawlResult(filename=f"{slug}.txt", source_url=url, content="", warning=f"error: {exc}")

    if len(resp.content) > _MAX_SIZE:
        return CrawlResult(filename=f"{slug}.txt", source_url=url, content="", warning="file too large")

    content_type = resp.headers.get("content-type", "")
    extractor = _get_extractor(content_type, url)
    is_pdf = isinstance(extractor, PdfExtractor)

    try:
        text = extractor.extract(resp.content, url)
    except Exception as exc:
        logger.warning(f"Extraction failed for {url}: {exc}")
        text = ""

    ext = ".pdf" if is_pdf else ".txt"
    return CrawlResult(filename=f"{slug}{ext}", source_url=url, content=text.strip(), is_pdf=is_pdf)
