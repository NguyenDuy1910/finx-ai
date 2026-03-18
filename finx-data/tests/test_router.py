"""Tests for the Input Router."""

import pytest

from pipeline.adapters.base import RawDocument
from pipeline.extractors.base import BaseExtractor
from pipeline.extractors.html import HTMLExtractor, MarkdownExtractor, SchemaExtractor
from pipeline.router import ContentCategory, InputRouter, classify
from pipeline.schemas.canonical import CanonicalDocument


# ── classify() tests ──────────────────────────────────────────────────────────


class TestClassify:
    def test_pdf_by_mime(self):
        raw = RawDocument(source_system="s3", source_uri="s3://bucket/report.pdf", mime_type="application/pdf")
        assert classify(raw) == ContentCategory.PDF

    def test_pdf_by_extension(self):
        raw = RawDocument(source_system="local", source_uri="/data/report.pdf")
        assert classify(raw) == ContentCategory.PDF

    def test_pdf_by_binary_magic(self):
        raw = RawDocument(source_system="local", source_uri="/data/report", binary_content=b"%PDF-1.4 ...")
        assert classify(raw) == ContentCategory.PDF

    def test_html_by_mime(self):
        raw = RawDocument(source_system="local", source_uri="/data/page.html", mime_type="text/html")
        assert classify(raw) == ContentCategory.HTML

    def test_html_by_raw_html_field(self):
        raw = RawDocument(source_system="confluence", source_uri="page/123", raw_html="<h1>Title</h1>")
        assert classify(raw) == ContentCategory.HTML

    def test_html_by_content_heuristic(self):
        raw = RawDocument(source_system="test", source_uri="test://x", raw_content="<html><body>hi</body></html>")
        assert classify(raw) == ContentCategory.HTML

    def test_markdown_by_mime(self):
        raw = RawDocument(source_system="local", source_uri="/data/readme.md", mime_type="text/markdown")
        assert classify(raw) == ContentCategory.MARKDOWN

    def test_markdown_by_extension(self):
        raw = RawDocument(source_system="local", source_uri="/data/file.markdown")
        assert classify(raw) == ContentCategory.MARKDOWN

    def test_schema_by_source_system(self):
        raw = RawDocument(source_system="athena", source_uri="athena://db/table")
        assert classify(raw) == ContentCategory.SCHEMA

    def test_schema_by_glue_source(self):
        raw = RawDocument(source_system="glue", source_uri="glue://catalog/db/t")
        assert classify(raw) == ContentCategory.SCHEMA

    def test_csv_by_mime(self):
        raw = RawDocument(source_system="local", source_uri="/data/file.csv", mime_type="text/csv")
        assert classify(raw) == ContentCategory.CSV

    def test_csv_by_extension(self):
        raw = RawDocument(source_system="local", source_uri="/data/file.tsv")
        assert classify(raw) == ContentCategory.CSV

    def test_json_by_mime(self):
        raw = RawDocument(source_system="local", source_uri="/data/file.json", mime_type="application/json")
        assert classify(raw) == ContentCategory.JSON

    def test_image_by_mime(self):
        raw = RawDocument(source_system="s3", source_uri="s3://b/img.png", mime_type="image/png")
        assert classify(raw) == ContentCategory.IMAGE

    def test_image_generic_mime(self):
        raw = RawDocument(source_system="s3", source_uri="s3://b/img.bmp", mime_type="image/bmp")
        assert classify(raw) == ContentCategory.IMAGE

    def test_plaintext_fallback(self):
        raw = RawDocument(source_system="test", source_uri="test://x", raw_content="Plain text.")
        assert classify(raw) == ContentCategory.PLAINTEXT

    def test_extension_with_query_params(self):
        raw = RawDocument(source_system="s3", source_uri="https://s3.example.com/file.pdf?token=abc")
        assert classify(raw) == ContentCategory.PDF


# ── InputRouter tests ─────────────────────────────────────────────────────────


class _DummyExtractor(BaseExtractor):
    name = "dummy"

    def __init__(self, label: str = "dummy"):
        self.name = label

    def extract(self, raw: RawDocument) -> CanonicalDocument:
        return CanonicalDocument(source_system=raw.source_system, source_uri=raw.source_uri, title=self.name)


class TestInputRouter:
    def test_route_returns_correct_extractor(self):
        html_ext = _DummyExtractor("html")
        md_ext = _DummyExtractor("md")
        table = {ContentCategory.HTML: html_ext, ContentCategory.MARKDOWN: md_ext}
        router = InputRouter(table)

        raw = RawDocument(source_system="test", source_uri="test.html", mime_type="text/html")
        cat, ext = router.route(raw)
        assert cat == ContentCategory.HTML
        assert ext is html_ext

    def test_route_returns_none_for_unregistered(self):
        router = InputRouter({ContentCategory.HTML: _DummyExtractor("html")})
        raw = RawDocument(source_system="test", source_uri="test.pdf", mime_type="application/pdf")
        cat, ext = router.route(raw)
        assert cat == ContentCategory.PDF
        assert ext is None

    def test_categories_property(self):
        table = {
            ContentCategory.HTML: _DummyExtractor("html"),
            ContentCategory.PDF: _DummyExtractor("pdf"),
        }
        router = InputRouter(table)
        assert set(router.categories) == {ContentCategory.HTML, ContentCategory.PDF}

    def test_schema_routed_by_source_system(self):
        schema_ext = _DummyExtractor("schema")
        router = InputRouter({ContentCategory.SCHEMA: schema_ext})
        raw = RawDocument(source_system="athena", source_uri="athena://db/t", raw_content="col info")
        cat, ext = router.route(raw)
        assert cat == ContentCategory.SCHEMA
        assert ext is schema_ext

    def test_confluence_routed_to_html(self):
        """Confluence source_system should always route to HTML extractor."""
        html_ext = _DummyExtractor("html")
        router = InputRouter({ContentCategory.HTML: html_ext})
        raw = RawDocument(
            source_system="confluence",
            source_uri="https://org.atlassian.net/wiki/spaces/X/pages/123",
            raw_content="# Title\n\nSome text",
            raw_html="<h1>Title</h1><p>Some text</p>",
        )
        cat, ext = router.route(raw)
        assert cat == ContentCategory.HTML
        assert ext is html_ext
