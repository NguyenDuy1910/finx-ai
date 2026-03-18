"""Document reader utilities — file bytes, URL, Confluence."""
from __future__ import annotations

import io
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _reader_classes() -> tuple[Any, Any, Any, Any, Any]:
    from agno.knowledge.reader.pdf_reader import PDFReader
    from agno.knowledge.reader.text_reader import TextReader
    from agno.knowledge.reader.website_reader import WebsiteReader

    try:
        from agno.knowledge.reader.pptx_reader import PPTXReader
    except Exception:
        PPTXReader = None

    try:
        from agno.knowledge.reader.excel_reader import ExcelReader
    except Exception:
        ExcelReader = None

    return PDFReader, TextReader, WebsiteReader, PPTXReader, ExcelReader


def extract_document_text(document: Any) -> str:
    for attr in ("content", "text", "body"):
        value = getattr(document, attr, None)
        if value:
            return str(value)
    return ""


def read_file_bytes(request: Any) -> str:
    if not request.content_bytes:
        raise ValueError("content_bytes is required for input_type=file_bytes")

    PDFReader, TextReader, _Web, PPTXReader, ExcelReader = _reader_classes()

    source_name = request.source_name or request.filename or "file_input"
    content_type = request.content_type.lower()
    suffix = Path(request.filename or source_name).suffix.lower()
    payload = io.BytesIO(request.content_bytes)

    try:
        if suffix == ".pdf" or "pdf" in content_type:
            docs = PDFReader().read(pdf=payload, name=source_name)
        elif suffix in {".ppt", ".pptx"} and PPTXReader is not None:
            docs = PPTXReader().read(file=payload, name=source_name)
        elif suffix in {".xls", ".xlsx"} and ExcelReader is not None:
            docs = ExcelReader().read(file=payload, name=source_name)
        else:
            docs = TextReader().read(file=payload, name=source_name)

        text = "\n\n".join(
            extract_document_text(doc) for doc in docs if extract_document_text(doc).strip()
        )
        if text.strip():
            return text
    except Exception as exc:
        logger.warning("Reader parse failed for %s: %s", source_name, exc)

    return request.content_bytes.decode("utf-8", errors="replace")


def read_url(request: Any) -> str:
    if not request.url:
        raise ValueError(f"url is required for input_type={request.input_type.value}")

    _PDF, TextReader, WebsiteReader, _PPTX, _Excel = _reader_classes()

    from src.knowledge.indexing.utils.models import IngestionInputType

    if request.input_type == IngestionInputType.CONFLUENCE:
        from src.knowledge.indexing.utils.doc_parser import fetch_url_content
        return fetch_url_content(
            request.url,
            confluence_base_url=request.confluence_base_url,
            confluence_username=request.confluence_username,
            confluence_api_token=request.confluence_api_token,
        )

    try:
        docs = WebsiteReader().read(url=request.url, name=request.source_name or request.url)
        text = "\n\n".join(
            extract_document_text(doc) for doc in docs if extract_document_text(doc).strip()
        )
        if text.strip():
            return text
    except Exception as exc:
        logger.warning("WebsiteReader failed for %s: %s", request.url, exc)

    from src.knowledge.indexing.utils.doc_parser import fetch_url_content
    raw_text = fetch_url_content(
        request.url,
        confluence_base_url=request.confluence_base_url,
        confluence_username=request.confluence_username,
        confluence_api_token=request.confluence_api_token,
    )
    docs = TextReader().read(
        file=io.BytesIO(raw_text.encode("utf-8")),
        name=request.source_name or request.url,
    )
    return "\n\n".join(
        extract_document_text(doc) for doc in docs if extract_document_text(doc).strip()
    )


def read_request_text(request: Any) -> str:
    from src.knowledge.indexing.utils.models import IngestionInputType

    if request.input_type == IngestionInputType.FILE_BYTES:
        return read_file_bytes(request)
    if request.input_type in {IngestionInputType.URL, IngestionInputType.CONFLUENCE}:
        return read_url(request)
    if request.input_type == IngestionInputType.TEXT:
        return (request.content_text or "").strip()
    raise ValueError(f"Unsupported input_type: {request.input_type}")
