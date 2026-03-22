"""Tests for the pipeline engine."""

import json
import tempfile
from pathlib import Path

import pytest

from pipeline.adapters.base import BaseAdapter, RawDocument
from pipeline.engine import PipelineConfig, PipelineEngine, PipelineResult
from pipeline.router import ContentCategory
from pipeline.schemas.canonical import CanonicalDocument
from pipeline.writers.json_writer import JSONWriter, ProgressTrackingWriter


class MockAdapter(BaseAdapter):
    source_system = "test"

    def __init__(self, docs: list[RawDocument]):
        self._docs = docs

    def fetch(self, **kwargs):
        yield from self._docs


class FailingAdapter(BaseAdapter):
    source_system = "test"

    def __init__(self):
        self._docs = [
            RawDocument(source_system="test", source_uri="test://1", raw_content="Hello world one"),
            RawDocument(source_system="test", source_uri="test://2", raw_content="Hello world two"),
        ]

    def fetch(self, **kwargs):
        yield self._docs[0]
        raise ConnectionError("Network failure")


def _make_docs(n: int = 3) -> list[RawDocument]:
    return [
        RawDocument(
            source_system="test",
            source_uri=f"test://doc-{i}",
            source_id=f"doc-{i}",
            title=f"Test Document {i}",
            raw_content=f"# Heading {i}\n\nThis is paragraph {i} with some content words.",
            mime_type="text/markdown",
        )
        for i in range(n)
    ]


class TestPipelineEngine:
    def test_basic_run(self):
        adapter = MockAdapter(_make_docs(3))
        config = PipelineConfig(use_docling=False)
        engine = PipelineEngine(config=config)
        result = engine.run(adapter)
        assert result.total_fetched == 3
        assert result.total_processed == 3
        assert result.total_errors == 0

    def test_error_handling(self):
        adapter = FailingAdapter()
        config = PipelineConfig(use_docling=False, min_doc_words=0)
        engine = PipelineEngine(config=config)
        result = engine.run(adapter)
        assert result.total_processed >= 1

    def test_extractor_selection_html(self):
        raw = RawDocument(
            source_system="test",
            source_uri="test://html",
            raw_html="<h1>Title</h1><p>Text content here</p>",
            raw_content="<h1>Title</h1><p>Text content here</p>",
        )
        config = PipelineConfig(use_docling=False, min_doc_words=0)
        engine = PipelineEngine(config=config)
        _, ext = engine.router.route(raw)
        assert ext is not None

    def test_skip_low_value_docs(self):
        raw = RawDocument(
            source_system="test",
            source_uri="test://tiny",
            raw_content="Hi",
            mime_type="text/markdown",
        )
        adapter = MockAdapter([raw])
        config = PipelineConfig(use_docling=False, min_doc_words=5)
        engine = PipelineEngine(config=config)
        result = engine.run(adapter)
        assert result.total_skipped == 1

    def test_rule_normalizer_applied(self):
        raw = RawDocument(
            source_system="test",
            source_uri="test://banking",
            raw_content="# NPL Report\n\nThe NPL ratio for CASA accounts under Basel II framework.",
            mime_type="text/markdown",
        )
        adapter = MockAdapter([raw])
        config = PipelineConfig(use_docling=False)
        engine = PipelineEngine(config=config)
        result = engine.run(adapter)
        assert result.total_processed == 1


class TestJSONWriter:
    def test_write_canonical(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = JSONWriter(tmpdir, format="canonical")
            doc = CanonicalDocument(
                source_system="test",
                source_uri="test://1",
                source_document_id="doc1",
                title="Test",
            )
            path = writer.write(doc)
            assert Path(path).exists()
            data = json.loads(Path(path).read_text())
            assert data["source_system"] == "test"
            assert data["document_id"] == doc.document_id

    def test_skip_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = JSONWriter(tmpdir, format="canonical", overwrite=False)
            doc = CanonicalDocument(
                source_system="test",
                source_uri="test://1",
                source_document_id="existing",
                title="Test",
            )
            path1 = writer.write(doc)
            path2 = writer.write(doc)
            assert path1 == path2

class TestProgressTrackingWriter:
    def test_skip_processed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inner = JSONWriter(tmpdir, format="canonical", overwrite=True)
            progress_file = Path(tmpdir) / ".progress.json"
            writer = ProgressTrackingWriter(inner, progress_file)

            doc = CanonicalDocument(source_system="test", source_uri="test://1", title="Test")
            path1 = writer.write(doc)
            assert path1 != ""
            writer.flush()

            writer2 = ProgressTrackingWriter(inner, progress_file)
            path2 = writer2.write(doc)
            assert path2 == ""


class TestPipelineIntegration:
    def test_full_pipeline_with_writer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = MockAdapter(_make_docs(5))
            writer = JSONWriter(tmpdir, format="canonical")
            config = PipelineConfig(use_docling=False)
            engine = PipelineEngine(config=config, writer=writer)
            result = engine.run(adapter)
            assert result.total_fetched == 5
            assert result.total_processed == 5
            output_files = list(Path(tmpdir).glob("*.json"))
            assert len(output_files) == 5

class TestRouterIntegration:
    def test_default_router_built(self):
        config = PipelineConfig(use_docling=False)
        engine = PipelineEngine(config=config)
        cats = engine.router.categories
        assert ContentCategory.HTML in cats
        assert ContentCategory.MARKDOWN in cats

    def test_router_routes_html(self):
        config = PipelineConfig(use_docling=False)
        engine = PipelineEngine(config=config)
        raw = RawDocument(source_system="confluence", source_uri="page/123", raw_html="<h1>Title</h1>")
        cat, ext = engine.router.route(raw)
        assert cat == ContentCategory.HTML
        assert ext is not None
        assert ext.name == "html_extractor"

    def test_router_routes_markdown(self):
        config = PipelineConfig(use_docling=False)
        engine = PipelineEngine(config=config)
        raw = RawDocument(source_system="local", source_uri="/data/readme.md", mime_type="text/markdown", raw_content="# Hello\n\nWorld")
        cat, ext = engine.router.route(raw)
        assert cat == ContentCategory.MARKDOWN


class TestConcurrentEngine:
    def test_llm_concurrency_config(self):
        config = PipelineConfig(use_llm_normalizer=True, use_docling=False, llm_concurrency=4)
        engine = PipelineEngine(config=config)
        assert config.llm_concurrency == 4

    def test_run_with_concurrency_no_llm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = MockAdapter(_make_docs(5))
            writer = JSONWriter(tmpdir, format="canonical")
            config = PipelineConfig(use_docling=False, llm_concurrency=4)
            engine = PipelineEngine(config=config, writer=writer)
            result = engine.run(adapter)
            assert result.total_processed == 5
            assert result.total_errors == 0
