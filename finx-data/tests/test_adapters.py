"""Tests for source adapters."""

import json
import tempfile
from pathlib import Path

import pytest

from pipeline.adapters.base import RawDocument
from pipeline.adapters.local import LocalFileAdapter


class TestRawDocument:
    def test_content_hash_deterministic(self):
        raw = RawDocument(source_system="test", source_uri="test://1", raw_content="hello")
        h1 = raw.content_hash
        h2 = raw.content_hash
        assert h1 == h2
        assert len(h1) == 64

    def test_content_hash_different_content(self):
        r1 = RawDocument(source_system="test", source_uri="test://1", raw_content="hello")
        r2 = RawDocument(source_system="test", source_uri="test://2", raw_content="world")
        assert r1.content_hash != r2.content_hash

    def test_binary_content_hash(self):
        raw = RawDocument(
            source_system="test",
            source_uri="test://1",
            binary_content=b"binary data",
        )
        assert len(raw.content_hash) == 64


class TestLocalFileAdapter:
    def test_read_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {"title": "Test", "content": "Hello world"}
            (Path(tmpdir) / "test.json").write_text(json.dumps(data))

            adapter = LocalFileAdapter(tmpdir)
            docs = list(adapter.fetch())

            assert len(docs) == 1
            assert docs[0].title == "Test"
            assert docs[0].source_system == "local"

    def test_read_json_array(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = [
                {"title": "Item 0", "content": "First"},
                {"title": "Item 1", "content": "Second"},
            ]
            (Path(tmpdir) / "items.json").write_text(json.dumps(data))

            adapter = LocalFileAdapter(tmpdir)
            docs = list(adapter.fetch())
            assert len(docs) == 2

    def test_read_markdown_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "readme.md").write_text("# Hello\n\nWorld")

            adapter = LocalFileAdapter(tmpdir)
            docs = list(adapter.fetch())

            assert len(docs) == 1
            assert docs[0].mime_type == "text/markdown"
            assert "Hello" in docs[0].raw_content

    def test_read_csv_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "data.csv").write_text("name,age\nAlice,30\nBob,25\n")

            adapter = LocalFileAdapter(tmpdir)
            docs = list(adapter.fetch())

            assert len(docs) == 1
            assert "name" in docs[0].raw_content
            assert docs[0].metadata["row_count"] == 2

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = LocalFileAdapter(tmpdir)
            docs = list(adapter.fetch())
            assert len(docs) == 0

    def test_nonexistent_directory(self):
        adapter = LocalFileAdapter("/nonexistent/path")
        docs = list(adapter.fetch())
        assert len(docs) == 0

    def test_skip_hidden_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".hidden.json").write_text('{"x": 1}')
            (Path(tmpdir) / "visible.json").write_text('{"x": 2}')

            adapter = LocalFileAdapter(tmpdir)
            docs = list(adapter.fetch())
            assert len(docs) == 1
            assert "visible" in docs[0].source_id

    def test_custom_globs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "data.json").write_text('{"x": 1}')
            (Path(tmpdir) / "readme.md").write_text("# Hello")
            (Path(tmpdir) / "notes.txt").write_text("Note")

            adapter = LocalFileAdapter(tmpdir)
            docs = list(adapter.fetch(globs=["*.json"]))
            assert len(docs) == 1
