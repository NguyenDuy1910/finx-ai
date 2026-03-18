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


# ── Test fixtures ─────────────────────────────────────────────────────────────


class MockAdapter(BaseAdapter):
    """Adapter that yields pre-built RawDocuments."""

    source_system = "test"

    def __init__(self, docs: list[RawDocument]):
        self._docs = docs

    def fetch(self, **kwargs):
        yield from self._docs


class FailingAdapter(BaseAdapter):
    """Adapter that raises on the second document."""

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


# ── Engine tests ──────────────────────────────────────────────────────────────


class TestPipelineEngine:
    def test_basic_run(self):
        adapter = MockAdapter(_make_docs(3))
        config = PipelineConfig(use_llm_normalizer=False, use_mineru=False)
        engine = PipelineEngine(config=config)
        result = engine.run(adapter)

        assert result.total_fetched == 3
        assert result.total_processed == 3
        assert result.total_errors == 0

    def test_process_single(self):
        raw = _make_docs(1)[0]
        config = PipelineConfig(use_llm_normalizer=False, use_mineru=False)
        engine = PipelineEngine(config=config)
        doc = engine.process_single(raw)

        assert doc is not None
        assert isinstance(doc, CanonicalDocument)
        assert doc.source_system == "test"
        assert doc.title == "Test Document 0"

    def test_error_handling(self):
        adapter = FailingAdapter()
        config = PipelineConfig(use_llm_normalizer=False, use_mineru=False, min_doc_words=0)
        engine = PipelineEngine(config=config)
        result = engine.run(adapter)

        # Should process at least 1 doc before failure
        assert result.total_processed >= 1

    def test_extractor_selection_html(self):
        raw = RawDocument(
            source_system="test",
            source_uri="test://html",
            raw_html="<h1>Title</h1><p>Text</p>",
            raw_content="<h1>Title</h1><p>Text</p>",
        )
        config = PipelineConfig(use_mineru=False, use_llm_normalizer=False, min_doc_words=0)
        engine = PipelineEngine(config=config)
        doc = engine.process_single(raw)
        assert doc is not None

    def test_extractor_selection_schema(self):
        raw = RawDocument(
            source_system="athena",
            source_uri="athena://db/table",
            raw_content="database: db\ntable: test",
            mime_type="application/x-schema",
            metadata={"database": "db", "table_name": "test", "columns": []},
        )
        config = PipelineConfig(use_mineru=False, use_llm_normalizer=False, min_doc_words=0)
        engine = PipelineEngine(config=config)
        doc = engine.process_single(raw)
        assert doc is not None
        assert doc.content_type == "schema"

    def test_skip_low_value_docs(self):
        """Documents with fewer words than min_doc_words are skipped."""
        raw = RawDocument(
            source_system="test",
            source_uri="test://tiny",
            raw_content="Hi",
            mime_type="text/markdown",
        )
        config = PipelineConfig(use_mineru=False, use_llm_normalizer=False, min_doc_words=5)
        engine = PipelineEngine(config=config)
        doc = engine.process_single(raw)
        assert doc is None  # skipped

    def test_rule_normalizer_applied(self):
        raw = RawDocument(
            source_system="test",
            source_uri="test://banking",
            raw_content="# NPL Report\n\nThe NPL ratio for CASA accounts under Basel II framework.",
            mime_type="text/markdown",
        )
        config = PipelineConfig(use_mineru=False, use_llm_normalizer=False)
        engine = PipelineEngine(config=config)
        doc = engine.process_single(raw)
        assert doc is not None
        assert "abbreviations" in doc.metadata
        assert "NPL" in doc.metadata["abbreviations"]


# ── Writer tests ──────────────────────────────────────────────────────────────


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

    def test_write_legacy_confluence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = JSONWriter(tmpdir, format="legacy")
            doc = CanonicalDocument(
                source_system="confluence",
                source_uri="test://page/123",
                source_document_id="123",
                title="Test Page",
                metadata={"space_key": "DATA"},
            )
            path = writer.write(doc)
            data = json.loads(Path(path).read_text())
            assert data["page_id"] == "123"
            assert data["space"] == "DATA"

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
            assert path1 == path2  # same path, file not rewritten

    def test_write_knowledge_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = JSONWriter(tmpdir, format="knowledge")
            doc = CanonicalDocument(
                source_system="confluence",
                source_uri="test://page/123",
                source_document_id="123",
                title="Test Page",
                tags=["compliance", "risk"],
                metadata={
                    "space_key": "DPO",
                    "summary": "A test summary",
                    "document_type": "policy",
                    "key_entities": ["NPL", "SBV"],
                    "quality_dimensions": {"clarity": 0.9},
                    "structured_content": {
                        "overview": "Policy about NPL.",
                        "business_rules": ["DPD > 90 = Group 5"],
                    },
                },
            )
            path = writer.write(doc)
            data = json.loads(Path(path).read_text())

            # Top-level knowledge fields
            assert data["document_id"] == doc.document_id
            assert data["document_type"] == "policy"
            assert data["summary"] == "A test summary"
            assert data["key_entities"] == ["NPL", "SBV"]
            assert data["space_key"] == "DPO"
            assert "text" in data
            assert "Test Page" in data["text"]
            assert data["quality_dimensions"]["clarity"] == 0.9
            assert data["structured_content"]["overview"] == "Policy about NPL."
            assert "compliance" in data["domains"]


class TestProgressTrackingWriter:
    def test_skip_processed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inner = JSONWriter(tmpdir, format="canonical", overwrite=True)
            progress_file = Path(tmpdir) / ".progress.json"
            writer = ProgressTrackingWriter(inner, progress_file)

            doc = CanonicalDocument(
                source_system="test",
                source_uri="test://1",
                title="Test",
            )

            # First write
            path1 = writer.write(doc)
            assert path1 != ""

            writer.flush()

            # Second write should be skipped
            writer2 = ProgressTrackingWriter(inner, progress_file)
            path2 = writer2.write(doc)
            assert path2 == ""  # skipped

    def test_flush_interval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inner = JSONWriter(tmpdir, format="canonical", overwrite=True)
            progress_file = Path(tmpdir) / ".progress.json"
            writer = ProgressTrackingWriter(inner, progress_file, flush_interval=2)

            for i in range(3):
                doc = CanonicalDocument(
                    source_system="test",
                    source_uri=f"test://{i}",
                    title=f"Doc {i}",
                )
                writer.write(doc)

            # Progress should have been flushed at least once (at doc 2)
            assert progress_file.exists()
            data = json.loads(progress_file.read_text())
            assert data["count"] >= 2


# ── Integration test ──────────────────────────────────────────────────────────


class TestPipelineIntegration:
    def test_full_pipeline_with_writer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = MockAdapter(_make_docs(5))
            writer = JSONWriter(tmpdir, format="canonical")
            config = PipelineConfig(use_llm_normalizer=False, use_mineru=False)
            engine = PipelineEngine(config=config, writer=writer)

            result = engine.run(adapter)

            assert result.total_fetched == 5
            assert result.total_processed == 5
            assert result.total_errors == 0

            output_files = list(Path(tmpdir).glob("*.json"))
            assert len(output_files) == 5

            # Verify content
            for f in output_files:
                data = json.loads(f.read_text())
                assert "source_system" in data
                assert "document_id" in data
                assert "content_blocks" in data

    def test_full_pipeline_legacy_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = MockAdapter(_make_docs(2))
            writer = JSONWriter(tmpdir, format="legacy")
            config = PipelineConfig(use_llm_normalizer=False, use_mineru=False)
            engine = PipelineEngine(config=config, writer=writer)

            result = engine.run(adapter)
            assert result.total_processed == 2

            output_files = list(Path(tmpdir).glob("*.json"))
            assert len(output_files) == 2

    def test_save_intermediate_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inter_dir = Path(tmpdir) / "intermediate"
            adapter = MockAdapter(_make_docs(3))
            writer = JSONWriter(tmpdir, format="canonical")
            config = PipelineConfig(
                use_llm_normalizer=False,
                use_mineru=False,
                save_intermediate=True,
                intermediate_dir=inter_dir,
            )
            engine = PipelineEngine(config=config, writer=writer)

            result = engine.run(adapter)
            assert result.total_processed == 3

            # Step 1 files
            step1_dir = inter_dir / "step1_extracted"
            assert step1_dir.exists()
            step1_files = list(step1_dir.glob("*.json"))
            assert len(step1_files) == 3

            # Step 2 files
            step2_dir = inter_dir / "step2_normalized"
            assert step2_dir.exists()
            step2_files = list(step2_dir.glob("*.json"))
            assert len(step2_files) == 3

            # Verify intermediate content is valid JSON with canonical schema
            for f in step1_files:
                data = json.loads(f.read_text())
                assert "source_system" in data
                assert "document_id" in data
                assert "content_blocks" in data

            # Step2 should have normalization provenance that step1 doesn't
            s1 = json.loads(step1_files[0].read_text())
            s2 = json.loads(step2_files[0].read_text())
            assert len(s2["provenance"]["steps"]) > len(s1["provenance"]["steps"])


# ── Artifact store + Router integration ───────────────────────────────────────


class TestArtifactStoreIntegration:
    def test_save_raw_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_dir = Path(tmpdir) / "raw_artifacts"
            adapter = MockAdapter(_make_docs(3))
            writer = JSONWriter(tmpdir, format="canonical")
            config = PipelineConfig(
                use_llm_normalizer=False,
                use_mineru=False,
                save_raw_artifacts=True,
                raw_artifact_dir=raw_dir,
            )
            engine = PipelineEngine(config=config, writer=writer)
            result = engine.run(adapter)

            assert result.total_processed == 3
            assert raw_dir.exists()

            manifest = raw_dir / "_manifest.json"
            assert manifest.exists()
            data = json.loads(manifest.read_text())
            assert data["artifact_count"] == 3

    def test_reprocess_from_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_dir = Path(tmpdir) / "raw_artifacts"
            out_dir = Path(tmpdir) / "output"

            # First run: fetch + store artifacts
            adapter = MockAdapter(_make_docs(3))
            writer = JSONWriter(str(out_dir), format="canonical")
            config = PipelineConfig(
                use_llm_normalizer=False,
                use_mineru=False,
                save_raw_artifacts=True,
                raw_artifact_dir=raw_dir,
            )
            engine = PipelineEngine(config=config, writer=writer)
            result1 = engine.run(adapter)
            assert result1.total_processed == 3

            # Second run: reprocess from stored artifacts (no adapter)
            out_dir2 = Path(tmpdir) / "output2"
            writer2 = JSONWriter(str(out_dir2), format="canonical")
            engine2 = PipelineEngine(
                config=PipelineConfig(
                    use_mineru=False,
                    raw_artifact_dir=raw_dir,
                ),
                writer=writer2,
            )
            result2 = engine2.reprocess()
            assert result2.total_fetched == 3
            assert result2.total_processed == 3


class TestRouterIntegration:
    def test_default_router_built(self):
        config = PipelineConfig(use_mineru=False, use_llm_normalizer=False)
        engine = PipelineEngine(config=config)
        cats = engine.router.categories
        # Should have at least HTML, SCHEMA, MARKDOWN, PLAINTEXT
        assert ContentCategory.HTML in cats
        assert ContentCategory.SCHEMA in cats
        assert ContentCategory.MARKDOWN in cats

    def test_router_routes_html(self):
        config = PipelineConfig(use_mineru=False, use_llm_normalizer=False)
        engine = PipelineEngine(config=config)
        raw = RawDocument(
            source_system="confluence",
            source_uri="page/123",
            raw_html="<h1>Title</h1><p>Text</p>",
        )
        cat, ext = engine.router.route(raw)
        assert cat == ContentCategory.HTML
        assert ext is not None
        assert ext.name == "html_extractor"

    def test_router_routes_schema(self):
        config = PipelineConfig(use_mineru=False, use_llm_normalizer=False)
        engine = PipelineEngine(config=config)
        raw = RawDocument(
            source_system="athena",
            source_uri="athena://db/table",
            raw_content="schema data",
            metadata={"database": "db", "table_name": "test", "columns": []},
        )
        cat, ext = engine.router.route(raw)
        assert cat == ContentCategory.SCHEMA
        assert ext is not None
        assert ext.name == "schema_extractor"

    def test_router_routes_markdown(self):
        config = PipelineConfig(use_mineru=False, use_llm_normalizer=False)
        engine = PipelineEngine(config=config)
        raw = RawDocument(
            source_system="local",
            source_uri="/data/readme.md",
            mime_type="text/markdown",
            raw_content="# Hello\n\nWorld",
        )
        cat, ext = engine.router.route(raw)
        assert cat == ContentCategory.MARKDOWN
        assert ext is not None


class TestKnowledgeFormatPipeline:
    """Integration test for the knowledge output format."""

    def test_knowledge_format_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = MockAdapter(_make_docs(3))
            writer = JSONWriter(tmpdir, format="knowledge")
            config = PipelineConfig(use_llm_normalizer=False, use_mineru=False)
            engine = PipelineEngine(config=config, writer=writer)

            result = engine.run(adapter)
            assert result.total_processed == 3

            output_files = list(Path(tmpdir).glob("*.json"))
            assert len(output_files) == 3

            for f in output_files:
                data = json.loads(f.read_text())
                # Knowledge format has these top-level fields
                assert "document_id" in data
                assert "text" in data  # the embedding text
                assert "document_type" in data
                assert "domains" in data
                assert "structured_content" in data
                assert "tables" in data


class TestConcurrentEngine:
    """Test that concurrent LLM processing works correctly."""

    def test_llm_concurrency_config(self):
        config = PipelineConfig(
            use_llm_normalizer=True,
            use_mineru=False,
            llm_concurrency=4,
        )
        engine = PipelineEngine(config=config)
        assert config.llm_concurrency == 4

    def test_run_with_concurrency_no_llm(self):
        """Even with llm_concurrency>1, should work fine when no LLM normalizer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = MockAdapter(_make_docs(5))
            writer = JSONWriter(tmpdir, format="canonical")
            config = PipelineConfig(
                use_llm_normalizer=False,
                use_mineru=False,
                llm_concurrency=4,
            )
            engine = PipelineEngine(config=config, writer=writer)
            result = engine.run(adapter)
            assert result.total_processed == 5
            assert result.total_errors == 0
