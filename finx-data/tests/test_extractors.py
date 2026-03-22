"""Tests for content extractors."""

import pytest

from pipeline.adapters.base import RawDocument
from pipeline.extractors.html import HTMLExtractor, MarkdownExtractor
from pipeline.schemas.blocks import (
    CodeBlock,
    HeadingBlock,
    ImageBlock,
    TableBlock,
    TextBlock,
)


# ── HTML Extractor ────────────────────────────────────────────────────────────


class TestHTMLExtractor:
    def setup_method(self):
        self.extractor = HTMLExtractor()

    def _make_raw(self, html: str, **kw) -> RawDocument:
        return RawDocument(
            source_system="test",
            source_uri="test://html",
            raw_content=html,
            raw_html=html,
            **kw,
        )

    def test_can_handle_html(self):
        raw = self._make_raw("<p>Hello</p>")
        assert self.extractor.can_handle(raw)

    def test_extract_text(self):
        raw = self._make_raw("<p>Hello world</p>")
        doc = self.extractor.extract(raw)
        text_blocks = [b for b in doc.content_blocks if isinstance(b, TextBlock)]
        assert any("Hello world" in b.content for b in text_blocks)

    def test_extract_headings(self):
        raw = self._make_raw("<h1>Title</h1><h2>Subtitle</h2>")
        doc = self.extractor.extract(raw)
        headings = [b for b in doc.content_blocks if isinstance(b, HeadingBlock)]
        assert len(headings) == 2
        assert headings[0].level == 1
        assert headings[0].content == "Title"
        assert headings[1].level == 2

    def test_extract_table(self):
        html = """
        <table>
            <tr><th>Name</th><th>Age</th></tr>
            <tr><td>Alice</td><td>30</td></tr>
            <tr><td>Bob</td><td>25</td></tr>
        </table>
        """
        raw = self._make_raw(html)
        doc = self.extractor.extract(raw)
        tables = [b for b in doc.content_blocks if isinstance(b, TableBlock)]
        assert len(tables) == 1
        assert tables[0].headers == ["Name", "Age"]
        assert len(tables[0].rows) == 2

    def test_extract_images(self):
        html = '<img src="/images/chart.png" alt="Revenue chart" />'
        raw = self._make_raw(html)
        doc = self.extractor.extract(raw)
        images = [b for b in doc.content_blocks if isinstance(b, ImageBlock)]
        assert len(images) == 1
        assert images[0].alt_text == "Revenue chart"

    def test_extract_code(self):
        html = "<code>SELECT * FROM users</code>"
        raw = self._make_raw(html)
        doc = self.extractor.extract(raw)
        codes = [b for b in doc.content_blocks if isinstance(b, CodeBlock)]
        assert len(codes) == 1
        assert "SELECT" in codes[0].content

    def test_extract_links(self):
        html = '<a href="https://example.com">Click here</a>'
        raw = self._make_raw(html)
        doc = self.extractor.extract(raw)
        assert len(doc.links) == 1
        assert doc.links[0].url == "https://example.com"
        assert doc.links[0].text == "Click here"

    def test_section_hierarchy(self):
        html = "<h1>Chapter</h1><p>text</p><h2>Section</h2><p>more</p>"
        raw = self._make_raw(html)
        doc = self.extractor.extract(raw)
        assert len(doc.section_hierarchy) >= 2


# ── Markdown Extractor ────────────────────────────────────────────────────────


class TestMarkdownExtractor:
    def setup_method(self):
        self.extractor = MarkdownExtractor()

    def _make_raw(self, content: str) -> RawDocument:
        return RawDocument(
            source_system="test",
            source_uri="test://md",
            raw_content=content,
            mime_type="text/markdown",
        )

    def test_can_handle_markdown(self):
        raw = self._make_raw("# Hello")
        assert self.extractor.can_handle(raw)

    def test_extract_headings(self):
        raw = self._make_raw("# Title\n\n## Section\n\n### Sub")
        doc = self.extractor.extract(raw)
        headings = [b for b in doc.content_blocks if isinstance(b, HeadingBlock)]
        assert len(headings) == 3

    def test_extract_code_block(self):
        raw = self._make_raw("```sql\nSELECT 1\n```")
        doc = self.extractor.extract(raw)
        codes = [b for b in doc.content_blocks if isinstance(b, CodeBlock)]
        assert len(codes) == 1
        assert codes[0].language == "sql"
        assert "SELECT" in codes[0].content

    def test_extract_links(self):
        raw = self._make_raw("See [docs](https://example.com/docs)")
        doc = self.extractor.extract(raw)
        assert len(doc.links) >= 1
        assert doc.links[0].url == "https://example.com/docs"

    def test_extract_images(self):
        raw = self._make_raw("![Chart](chart.png)")
        doc = self.extractor.extract(raw)
        images = [b for b in doc.content_blocks if isinstance(b, ImageBlock)]
        assert len(images) == 1

