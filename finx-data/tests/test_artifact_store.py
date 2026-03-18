"""Tests for the Raw Artifact Store."""

import json
import tempfile
from pathlib import Path

import pytest

from pipeline.adapters.base import RawDocument
from pipeline.artifact_store import ArtifactManifest, RawArtifactStore


# ── ArtifactManifest tests ────────────────────────────────────────────────────


class TestArtifactManifest:
    def test_add_and_has(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = ArtifactManifest(Path(tmpdir) / "manifest.json")
            assert not manifest.has("abc123")
            manifest.add("abc123", {"source": "test"})
            assert manifest.has("abc123")
            assert manifest.count == 1

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            m1 = ArtifactManifest(path)
            m1.add("hash1", {"source": "test", "title": "Doc 1"})
            m1.add("hash2", {"source": "test", "title": "Doc 2"})
            m1.save()

            m2 = ArtifactManifest(path)
            assert m2.count == 2
            assert m2.has("hash1")
            assert m2.has("hash2")

    def test_get_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = ArtifactManifest(Path(tmpdir) / "manifest.json")
            manifest.add("abc", {"title": "Test"})
            entry = manifest.get("abc")
            assert entry is not None
            assert entry["title"] == "Test"

    def test_get_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = ArtifactManifest(Path(tmpdir) / "manifest.json")
            assert manifest.get("missing") is None

    def test_all_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = ArtifactManifest(Path(tmpdir) / "manifest.json")
            manifest.add("a", {"x": 1})
            manifest.add("b", {"x": 2})
            entries = manifest.all_entries()
            assert len(entries) == 2


# ── RawArtifactStore tests ────────────────────────────────────────────────────


def _make_raw(n: int = 0) -> RawDocument:
    return RawDocument(
        source_system="test",
        source_uri=f"test://doc-{n}",
        source_id=f"doc-{n}",
        title=f"Test Document {n}",
        raw_content=f"Content of document {n}",
        mime_type="text/plain",
        metadata={"index": n},
    )


class TestRawArtifactStore:
    def test_store_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RawArtifactStore(tmpdir)
            raw = _make_raw(1)
            meta_path = store.store(raw)
            store.flush()

            assert Path(meta_path).exists()
            loaded = store.load_raw_document(meta_path)
            assert loaded.source_system == "test"
            assert loaded.source_uri == "test://doc-1"
            assert loaded.raw_content == "Content of document 1"

    def test_skip_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RawArtifactStore(tmpdir)
            raw = _make_raw(1)
            store.store(raw)
            store.flush()

            # Store same doc again — should skip
            store2 = RawArtifactStore(tmpdir)
            assert store2.manifest.count == 1
            store2.store(raw, skip_existing=True)
            assert store2.manifest.count == 1

    def test_store_with_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RawArtifactStore(tmpdir)
            raw = RawDocument(
                source_system="confluence",
                source_uri="page/123",
                source_id="page_123",
                title="My Page",
                raw_content="My Page content",
                raw_html="<h1>My Page</h1><p>content</p>",
            )
            meta_path = store.store(raw)
            store.flush()

            loaded = store.load_raw_document(meta_path)
            assert loaded.raw_html == "<h1>My Page</h1><p>content</p>"

    def test_store_binary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RawArtifactStore(tmpdir)
            raw = RawDocument(
                source_system="s3",
                source_uri="s3://bucket/file.pdf",
                source_id="file_pdf",
                title="Report",
                binary_content=b"%PDF-1.4 fake content",
                mime_type="application/pdf",
            )
            meta_path = store.store(raw)
            store.flush()

            loaded = store.load_raw_document(meta_path)
            assert loaded.binary_content == b"%PDF-1.4 fake content"

    def test_iter_stored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RawArtifactStore(tmpdir)
            for i in range(3):
                store.store(_make_raw(i))
            store.flush()

            store2 = RawArtifactStore(tmpdir)
            docs = store2.iter_stored()
            assert len(docs) == 3
            uris = {d.source_uri for d in docs}
            assert uris == {"test://doc-0", "test://doc-1", "test://doc-2"}

    def test_manifest_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RawArtifactStore(tmpdir)
            store.store(_make_raw(0))
            store.flush()

            manifest_path = Path(tmpdir) / "_manifest.json"
            assert manifest_path.exists()
            data = json.loads(manifest_path.read_text())
            assert data["artifact_count"] == 1
            assert "artifacts" in data

    def test_directory_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RawArtifactStore(tmpdir)
            store.store(_make_raw(0))
            store.flush()

            # Should have a subdirectory for the source system
            source_dir = Path(tmpdir) / "test"
            assert source_dir.exists()
            files = list(source_dir.iterdir())
            assert len(files) >= 2  # .content + .meta.json
