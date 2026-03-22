"""ChunkerRouter: dispatch CanonicalDocument to correct chunker."""

from __future__ import annotations

from pipeline.schemas.canonical import CanonicalDocument
from pipeline.chunkers.base import BaseChunker
from pipeline.chunkers.confluence_chunker import ConfluenceChunker
from pipeline.chunkers.document_chunker import DocumentChunker
from pipeline.chunkers.excel_chunker import ExcelChunker
from pipeline.chunkers.html_chunker import HTMLChunker
from pipeline.chunkers.table_chunker import TableChunker


class ChunkerRouter:
    """Routes CanonicalDocument to the correct chunker based on source_system and content_type."""

    def __init__(
        self,
        *,
        max_tokens: int = 400,
        overlap_tokens: int = 50,
        min_chunk_words: int = 10,
        default_tenant_id: str = "default",
    ) -> None:
        """Initialize router with chunker parameters.

        Args:
            max_tokens: Max tokens per chunk
            overlap_tokens: Token overlap between chunks
            min_chunk_words: Minimum words to produce a chunk
            default_tenant_id: Default tenant ID
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.min_chunk_words = min_chunk_words
        self.default_tenant_id = default_tenant_id

        # Initialize chunkers (reuse instances)
        self.confluence_chunker = ConfluenceChunker(
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            min_chunk_words=min_chunk_words,
            default_tenant_id=default_tenant_id,
        )
        self.document_chunker = DocumentChunker(
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            min_chunk_words=min_chunk_words,
            default_tenant_id=default_tenant_id,
        )
        self.table_chunker = TableChunker(
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            min_chunk_words=min_chunk_words,
            default_tenant_id=default_tenant_id,
        )
        self.excel_chunker = ExcelChunker(
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            min_chunk_words=min_chunk_words,
            default_tenant_id=default_tenant_id,
        )
        self.html_chunker = HTMLChunker(
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            min_chunk_words=min_chunk_words,
            default_tenant_id=default_tenant_id,
        )

    def route(self, doc: CanonicalDocument) -> BaseChunker:
        """Route a CanonicalDocument to the correct chunker.

        Decision tree:
        1. Confluence: all content types → ConfluenceChunker (it dispatches
           internally by source_content_type: page/blogpost/comment/attachment)
           Exception: attachment with PDF/DOCX extension → DocumentChunker;
           attachment with XLSX/CSV → ExcelChunker.
        2. Jira: → JiraChunker (imported lazily)
        3. Excel extensions → ExcelChunker
        4. section_hierarchy present → DocumentChunker
        5. Default: HTMLChunker

        Args:
            doc: CanonicalDocument to route

        Returns:
            BaseChunker instance for this document
        """
        # Rule 1: Confluence — type-aware routing
        if doc.source_system == "confluence":
            sct = (doc.source_content_type or doc.metadata.get("content_type", "")).lower()

            if sct == "attachment":
                mime = doc.metadata.get("media_type", "")
                filename = (doc.metadata.get("filename", "") or doc.title or "").lower()
                # Binary document attachments → specialised chunker
                if mime.startswith("application/pdf") or filename.endswith(".pdf"):
                    return self.document_chunker
                if any(filename.endswith(e) for e in (".docx", ".pptx")):
                    return self.document_chunker
                if any(filename.endswith(e) for e in (".xlsx", ".xls", ".csv", ".tsv")):
                    return self.excel_chunker
                # Images and other attachment types → ConfluenceChunker handles them
            return self.confluence_chunker

        # Rule 2: Jira
        if doc.source_system == "jira":
            return self._get_jira_chunker()

        # Rule 3: Excel extensions
        source_uri_lower = (doc.source_uri or "").lower()
        excel_exts = (".xlsx", ".xls", ".csv", ".tsv")
        if any(source_uri_lower.endswith(ext) for ext in excel_exts):
            return self.excel_chunker

        # Rule 4: Section hierarchy present (from DoclingExtractor output)
        if doc.section_hierarchy:
            return self.document_chunker

        # Rule 5: Default fallback
        return self.html_chunker

    def _get_jira_chunker(self) -> BaseChunker:
        """Lazily import and cache JiraChunker."""
        if not hasattr(self, "_jira_chunker"):
            from pipeline.chunkers.jira_chunker import JiraChunker
            self._jira_chunker = JiraChunker(
                max_tokens=self.max_tokens,
                overlap_tokens=self.overlap_tokens,
                min_chunk_words=self.min_chunk_words,
                default_tenant_id=self.default_tenant_id,
            )
        return self._jira_chunker
