"""Tests for canonical document schema and content blocks."""

from datetime import datetime, timezone

import pytest

from pipeline.schemas.blocks import (
    BlockType,
    CodeBlock,
    HeadingBlock,
    ImageBlock,
    LinkRef,
    ListBlock,
    SectionNode,
    TableBlock,
    TextBlock,
)
from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.provenance import (
    ProcessingStage,
    ProcessingStep,
    Provenance,
    QualitySignal,
)


# ── Block types ───────────────────────────────────────────────────────────────


class TestBlocks:
    def test_text_block(self):
        b = TextBlock(content="Hello world")
        assert b.block_type == BlockType.TEXT
        assert b.content == "Hello world"
        assert b.language is None

    def test_heading_block(self):
        b = HeadingBlock(content="Section 1", level=2)
        assert b.block_type == BlockType.HEADING
        assert b.level == 2

    def test_table_block(self):
        b = TableBlock(
            headers=["Name", "Age"],
            rows=[["Alice", "30"], ["Bob", "25"]],
            markdown="| Name | Age |\n| --- | --- |\n| Alice | 30 |\n| Bob | 25 |",
            caption="People",
        )
        assert b.block_type == BlockType.TABLE
        assert len(b.rows) == 2
        assert b.caption == "People"

    def test_image_block(self):
        b = ImageBlock(src="/images/chart.png", alt_text="Revenue chart")
        assert b.block_type == BlockType.IMAGE
        assert b.alt_text == "Revenue chart"

    def test_code_block(self):
        b = CodeBlock(content="SELECT * FROM t", language="sql")
        assert b.block_type == BlockType.CODE
        assert b.language == "sql"

    def test_list_block(self):
        b = ListBlock(items=["item1", "item2"], ordered=True)
        assert b.block_type == BlockType.LIST
        assert b.ordered is True

    def test_link_ref(self):
        link = LinkRef(url="https://example.com", text="Example", context="See Example")
        assert link.url == "https://example.com"

    def test_section_node(self):
        node = SectionNode(
            title="Introduction",
            level=1,
            path=["Introduction"],
            block_indices=[0, 1, 2],
        )
        assert node.title == "Introduction"
        assert len(node.block_indices) == 3


# ── Provenance ────────────────────────────────────────────────────────────────


class TestProvenance:
    def test_processing_step(self):
        step = ProcessingStep(
            stage=ProcessingStage.EXTRACTION,
            processor="html_extractor",
            duration_ms=42.5,
        )
        assert step.stage == ProcessingStage.EXTRACTION
        assert step.duration_ms == 42.5
        assert step.error is None

    def test_quality_signal(self):
        q = QualitySignal(
            extraction_confidence=0.9,
            word_count=500,
            has_tables=True,
        )
        assert q.extraction_confidence == 0.9
        assert q.has_tables is True
        assert q.has_images is False

    def test_provenance_add_step(self):
        prov = Provenance()
        step = ProcessingStep(
            stage=ProcessingStage.EXTRACTION,
            processor="test",
        )
        prov.add_step(step)
        assert len(prov.steps) == 1
        assert prov.last_stage == ProcessingStage.EXTRACTION
        assert not prov.has_errors

    def test_provenance_detects_errors(self):
        prov = Provenance()
        prov.add_step(
            ProcessingStep(
                stage=ProcessingStage.NORMALIZATION,
                processor="test",
                error="Something failed",
            )
        )
        assert prov.has_errors


# ── CanonicalDocument ─────────────────────────────────────────────────────────


class TestCanonicalDocument:
    def test_auto_document_id(self):
        doc = CanonicalDocument(
            source_system="confluence",
            source_uri="https://example.com/wiki/pages/123",
        )
        assert doc.document_id != ""
        assert len(doc.document_id) == 64  # SHA-256 hex length

    def test_deterministic_document_id(self):
        doc1 = CanonicalDocument(
            source_system="confluence",
            source_uri="https://example.com/wiki/pages/123",
        )
        doc2 = CanonicalDocument(
            source_system="confluence",
            source_uri="https://example.com/wiki/pages/123",
        )
        assert doc1.document_id == doc2.document_id

    def test_different_sources_different_ids(self):
        doc1 = CanonicalDocument(
            source_system="confluence",
            source_uri="https://example.com/wiki/pages/123",
        )
        doc2 = CanonicalDocument(
            source_system="confluence",
            source_uri="https://example.com/wiki/pages/456",
        )
        assert doc1.document_id != doc2.document_id

    def test_explicit_document_id(self):
        doc = CanonicalDocument(
            document_id="custom-id",
            source_system="test",
            source_uri="test://1",
        )
        assert doc.document_id == "custom-id"

    def test_full_text(self):
        doc = CanonicalDocument(
            source_system="test",
            source_uri="test://1",
            content_blocks=[
                TextBlock(content="Hello"),
                TextBlock(content="World"),
            ],
        )
        assert doc.full_text() == "Hello\n\nWorld"

    def test_word_count(self):
        doc = CanonicalDocument(
            source_system="test",
            source_uri="test://1",
            content_blocks=[
                TextBlock(content="The quick brown fox"),
            ],
        )
        assert doc.word_count() == 4

    def test_to_embedding_chunks(self):
        text = " ".join(f"word{i}" for i in range(100))
        doc = CanonicalDocument(
            source_system="test",
            source_uri="test://1",
            title="Test Doc",
            content_blocks=[TextBlock(content=text)],
        )
        chunks = doc.to_embedding_chunks(max_tokens=30, overlap=5)
        assert len(chunks) > 1
        assert chunks[0]["document_id"] == doc.document_id
        assert chunks[0]["title"] == "Test Doc"
        assert "word0" in chunks[0]["text"]

    def test_to_graph_payload(self):
        doc = CanonicalDocument(
            source_system="confluence",
            source_uri="test://1",
            source_document_id="123",
            title="Test",
            content_blocks=[
                TextBlock(content="Hello"),
                TableBlock(
                    headers=["A", "B"],
                    rows=[["1", "2"]],
                    markdown="| A | B |\n| 1 | 2 |",
                ),
            ],
            links=[LinkRef(url="https://example.com", text="Link")],
            tags=["lending"],
        )
        payload = doc.to_graph_payload()
        assert payload["document_id"] == doc.document_id
        assert payload["source_system"] == "confluence"
        assert len(payload["tables"]) == 1
        assert len(payload["links"]) == 1

    def test_serialization_roundtrip(self):
        import json

        doc = CanonicalDocument(
            source_system="test",
            source_uri="test://roundtrip",
            title="Roundtrip Test",
            content_blocks=[
                TextBlock(content="Hello"),
                HeadingBlock(content="Section", level=2),
            ],
            metadata={"key": "value"},
            tags=["test"],
        )
        data = json.loads(doc.model_dump_json())
        assert data["source_system"] == "test"
        assert data["title"] == "Roundtrip Test"
        assert len(data["content_blocks"]) == 2
        assert data["metadata"]["key"] == "value"
