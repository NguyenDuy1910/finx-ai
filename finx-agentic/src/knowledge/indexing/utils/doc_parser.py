from __future__ import annotations

import csv
import html.parser
import io
import logging
import mimetypes
import os
import re
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plain text helpers
# ---------------------------------------------------------------------------

def extract_text_from_txt(raw_bytes: bytes, encoding: str = "utf-8") -> str:
    """Decode raw bytes as UTF-8 text (fallback to latin-1)."""
    try:
        return raw_bytes.decode(encoding)
    except UnicodeDecodeError:
        return raw_bytes.decode("latin-1", errors="replace")


def extract_text_from_csv(raw_bytes: bytes) -> str:
    """Convert CSV bytes to a readable tabular text representation."""
    text = extract_text_from_txt(raw_bytes)
    reader = csv.reader(io.StringIO(text))
    lines = []
    for i, row in enumerate(reader):
        lines.append(" | ".join(row))
        if i >= 500:   # cap at 500 rows to avoid huge prompts
            lines.append("... (truncated)")
            break
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------

def extract_text_from_pdf(raw_bytes: bytes) -> str:
    """Extract text from PDF bytes.

    Tries ``pymupdf`` (fitz) first, then ``pdfplumber``.
    Raises ``ImportError`` if neither is installed.
    """
    try:
        import fitz  # pymupdf  # noqa: PLC0415  pylint: disable=import-outside-toplevel

        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        parts = []
        for page in doc:
            parts.append(page.get_text())
        return "\n".join(parts)
    except ImportError:
        pass

    try:
        import pdfplumber  # noqa: PLC0415  pylint: disable=import-outside-toplevel

        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError:
        pass

    raise ImportError(
        "PDF parsing requires 'pymupdf' or 'pdfplumber'. "
        "Install one: uv add pymupdf  OR  uv add pdfplumber"
    )


# ---------------------------------------------------------------------------
# Excel helpers
# ---------------------------------------------------------------------------

def extract_text_from_excel(raw_bytes: bytes) -> str:
    """Extract text from .xlsx bytes (requires ``openpyxl``)."""
    try:
        import openpyxl  # noqa: PLC0415  pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "Excel parsing requires 'openpyxl'. Install: uv add openpyxl"
        ) from exc

    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    parts = []
    for sheet in wb.worksheets:
        parts.append(f"=== Sheet: {sheet.title} ===")
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            parts.append(" | ".join("" if v is None else str(v) for v in row))
            if i >= 500:
                parts.append("... (truncated)")
                break
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# HTML / URL helpers
# ---------------------------------------------------------------------------

class _HTMLTextExtractor(html.parser.HTMLParser):
    """Minimal HTML → plain-text converter (no external deps)."""

    _skip_tags = {"script", "style", "head", "nav", "footer", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in self._skip_tags:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return "\n".join(self._parts)


_CONFLUENCE_PAGE_PATTERN = re.compile(
    r"https?://[^/]+/wiki/spaces/[^/]+/pages/(\d+)",
)
_CONFLUENCE_DISPLAY_PATTERN = re.compile(
    r"https?://[^/]+/wiki/display/([^/]+)/",
)


def _is_confluence_url(url: str) -> bool:
    return bool(
        _CONFLUENCE_PAGE_PATTERN.search(url)
        or _CONFLUENCE_DISPLAY_PATTERN.search(url)
        or "/wiki/" in url
    )


def _extract_confluence_base_url(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    wiki_idx = parsed.path.find("/wiki")
    base_path = parsed.path[:wiki_idx] if wiki_idx >= 0 else ""
    return f"{parsed.scheme}://{parsed.netloc}{base_path}"


def _extract_confluence_page_id(url: str) -> Optional[str]:
    match = _CONFLUENCE_PAGE_PATTERN.search(url)
    if match:
        return match.group(1)
    return None


def _strip_html_tags(raw_html: str) -> str:
    parser = _HTMLTextExtractor()
    try:
        parser.feed(raw_html)
    except html.parser.HTMLParseError:
        pass
    return parser.get_text()


class ConfluenceContent:
    """Result of Confluence page extraction, carrying both text and HTML."""

    __slots__ = ("text", "html", "title")

    def __init__(self, text: str, html: str = "", title: str = "") -> None:
        self.text = text
        self.html = html
        self.title = title

    def __str__(self) -> str:
        return self.text


def extract_text_from_confluence(
    url: str,
    *,
    base_url: Optional[str] = None,
    username: Optional[str] = None,
    api_token: Optional[str] = None,
) -> ConfluenceContent:
    confluence_base = (
        base_url
        or os.getenv("CONFLUENCE_BASE_URL")
        or os.getenv("CONFLUENCE_URL")
        or _extract_confluence_base_url(url)
    )
    user = username or os.getenv("CONFLUENCE_USERNAME", "")
    token = (
        api_token
        or os.getenv("CONFLUENCE_API_TOKEN")
        or os.getenv("CONFLUENCE_API_KEY")
        or ""
    )

    if not user or not token:
        logger.warning("No Confluence credentials configured, falling back to plain HTTP fetch")
        plain = extract_text_from_url(url)
        return ConfluenceContent(text=plain)

    try:
        from atlassian import Confluence
    except ImportError as exc:
        raise ImportError(
            "Confluence fetching requires 'atlassian-python-api'. "
            "Install: uv add atlassian-python-api"
        ) from exc

    confluence = Confluence(url=confluence_base, username=user, password=token)

    page_id = _extract_confluence_page_id(url)
    if page_id:
        page = confluence.get_page_by_id(page_id, expand="body.storage")
    else:
        title = url.rstrip("/").split("/")[-1].replace("+", " ").replace("%20", " ")
        space_match = _CONFLUENCE_DISPLAY_PATTERN.search(url)
        space_key = space_match.group(1) if space_match else None
        if space_key:
            page = confluence.get_page_by_title(space_key, title, expand="body.storage")
        else:
            logger.warning("Could not parse Confluence URL structure: %s", url)
            plain = extract_text_from_url(url)
            return ConfluenceContent(text=plain)

    if not page:
        raise ValueError(f"Confluence page not found for URL: {url}")

    page_title = page.get("title", "")
    body_html = page.get("body", {}).get("storage", {}).get("value", "")
    plain_text = _strip_html_tags(body_html)

    text = f"# {page_title}\n\n{plain_text}" if page_title else plain_text
    return ConfluenceContent(text=text, html=body_html, title=page_title)


def extract_text_from_url(url: str, *, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FinxBot/1.0 (schema-enricher context fetcher)",
            "Accept": "text/html,application/xhtml+xml,text/plain",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read()

    if "text/plain" in content_type:
        return extract_text_from_txt(raw)

    parser = _HTMLTextExtractor()
    try:
        parser.feed(raw.decode("utf-8", errors="replace"))
    except html.parser.HTMLParseError:
        pass
    return parser.get_text()


def fetch_url_content(
    url: str,
    *,
    confluence_base_url: Optional[str] = None,
    confluence_username: Optional[str] = None,
    confluence_api_token: Optional[str] = None,
) -> str | ConfluenceContent:
    """Fetch page content. Returns ConfluenceContent for Confluence URLs, plain str otherwise."""
    if _is_confluence_url(url):
        return extract_text_from_confluence(
            url,
            base_url=confluence_base_url,
            username=confluence_username,
            api_token=confluence_api_token,
        )
    return extract_text_from_url(url)


def extract_text(
    raw_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
) -> str:
    ext = Path(filename).suffix.lower()
    mime = content_type or mimetypes.guess_type(filename)[0] or ""

    if ext == ".pdf" or "pdf" in mime:
        return extract_text_from_pdf(raw_bytes)

    if ext in {".xlsx", ".xls"} or "spreadsheet" in mime or "excel" in mime:
        return extract_text_from_excel(raw_bytes)

    if ext == ".csv" or "csv" in mime:
        return extract_text_from_csv(raw_bytes)

    return extract_text_from_txt(raw_bytes)
