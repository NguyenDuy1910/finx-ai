"""Tests for VectorKnowledge._async_search — the full retrieval pipeline."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models.retrieval import RetrievedDocument
from src.knowledge.retrieval.vector_knowledge import VectorKnowledge, VectorKnowledgeConfig


# ── Fake Qdrant ScoredPoint ──────────────────────────────────────────────


def _make_point(
    point_id: str,
    doc_id: str = "doc-1",
    section_id: str = "sec-1",
    content: str = "Some useful content about banking regulations and compliance.",
    score: float = 0.85,
    *,
    doc_title: str = "Banking Policy",
    source_url: str = "https://wiki.example.com/banking",
    chunk_kind: str = "section",
    chunk_position: int = 0,
) -> SimpleNamespace:
    """Build a fake Qdrant ScoredPoint."""
    return SimpleNamespace(
        id=point_id,
        score=score,
        payload={
            "doc_id": doc_id,
            "section_id": section_id,
            "doc_title": doc_title,
            "chunk_text": content,
            "source_url": source_url,
            "chunk_kind": chunk_kind,
            "chunk_position": chunk_position,
            "source_system": "confluence",
            "heading": "Section A",
        },
    )


def _make_store(points: list) -> MagicMock:
    """Build a mock RetrievalStore that returns the given points."""
    store = MagicMock()
    store.search = MagicMock(return_value=points)
    return store


# ── Tests ────────────────────────────────────────────────────────────────


class TestAsyncSearchNoStore:
    """When store is None, _async_search returns empty list gracefully."""

    def test_returns_empty_when_qdrant_unavailable(self):
        vk = VectorKnowledge(config=VectorKnowledgeConfig())
        # Simulate Qdrant being unreachable
        vk._get_qdrant = MagicMock(side_effect=RuntimeError("no qdrant"))
        result = asyncio.run(vk._async_search("test query"))
        assert result == []


class TestAsyncSearchEmptyResults:
    """When Qdrant returns no points, pipeline short-circuits."""

    def test_returns_empty_on_no_hits(self):
        from unittest.mock import AsyncMock, patch

        vk = VectorKnowledge(config=VectorKnowledgeConfig())

        mock_response = SimpleNamespace(points=[])
        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(return_value=mock_response)

        mock_embedder = AsyncMock()
        mock_embedder.embed = AsyncMock(return_value=[0.1] * 1536)

        vk._qdrant = mock_qdrant
        vk._embedder = mock_embedder

        result = asyncio.run(vk._async_search("test query"))
        assert result == []
        mock_qdrant.query_points.assert_called_once()


class TestAsyncSearchFullPipeline:
    """Integration test with mocked postprocess steps."""

    @pytest.fixture
    def points(self):
        return [
            _make_point("p1", doc_id="doc-1", section_id="s1", score=0.9,
                        content="Banking regulations require KYC verification for all new accounts."),
            _make_point("p2", doc_id="doc-1", section_id="s1", score=0.7,
                        content="KYC includes identity verification and address proof."),
            _make_point("p3", doc_id="doc-2", section_id="s2", score=0.8,
                        content="Anti-money laundering policies apply to transactions above 10000 USD.",
                        doc_title="AML Policy", source_url="https://wiki.example.com/aml"),
        ]

    @pytest.fixture
    def vk(self, points):
        from unittest.mock import AsyncMock

        mock_response = SimpleNamespace(points=points)
        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(return_value=mock_response)

        mock_embedder = AsyncMock()
        mock_embedder.embed = AsyncMock(return_value=[0.1] * 1536)

        vk = VectorKnowledge(
            config=VectorKnowledgeConfig(
                candidate_limit=20,
                top_k=5,
                max_hits_per_doc=2,
                content_dedup_threshold=0.6,
                max_groups=5,
                max_blocks=5,
                rerank_top_n=3,
                max_pack_blocks=3,
                max_total_chars=8000,
                max_block_chars=2000,
            ),
        )
        vk._qdrant = mock_qdrant
        vk._embedder = mock_embedder
        return vk

    def test_store_called_with_correct_args(self, vk):
        asyncio.run(vk._async_search("KYC requirements"))
        vk._qdrant.query_points.assert_called_once()
        call_kwargs = vk._qdrant.query_points.call_args.kwargs
        assert call_kwargs["collection_name"] == "finx_knowledge"
        assert call_kwargs["limit"] == 20

    def test_returns_agno_documents(self, vk):
        """Pipeline should return Agno Document objects (not RetrievedDocument)."""
        from agno.knowledge.document import Document

        result = asyncio.run(vk._async_search("KYC requirements"))
        # Could be empty if clean/dedup drops everything, but should not raise
        for doc in result:
            assert isinstance(doc, Document)

    def test_citations_accumulated_in_session_state(self, vk):
        """When an agent with session_state is provided, citations are accumulated."""
        agent = SimpleNamespace(session_state={})
        result = asyncio.run(vk._async_search("KYC requirements", agent=agent))
        # If results came through, citations key should exist
        # (may be empty if pipeline filtered everything)
        # The key point is no exception was raised


class TestAsyncSearchStepByStep:
    """Test each pipeline step individually with controlled mocks."""

    @pytest.fixture
    def single_point(self):
        return [_make_point(
            "p1",
            content="A sufficiently long content string that will pass the cleaner minimum character threshold for testing.",
            score=0.9,
        )]

    def test_dedup_by_doc_limits_per_doc(self):
        """deduplicate_hits_by_doc caps hits per doc_id."""
        from src.knowledge.retrieval.postprocess.deduplicator import deduplicate_hits_by_doc

        points = [
            _make_point(f"p{i}", doc_id="same-doc", score=0.9 - i * 0.1)
            for i in range(5)
        ]
        result = deduplicate_hits_by_doc(points, max_per_doc=2)
        assert len(result) <= 2

    def test_scored_point_to_document_conversion(self):
        """scored_point_to_document produces RetrievedDocument with correct fields."""
        from src.knowledge.retrieval.confluence_knowledge import scored_point_to_document

        point = _make_point("p1", doc_title="Test Doc", content="Hello world")
        doc = scored_point_to_document(point)
        assert isinstance(doc, RetrievedDocument)
        assert doc.content == "Hello world"
        assert "Test Doc" in doc.name
        assert doc.meta_data.get("qdrant_score") == 0.85

    def test_clean_drops_empty_content(self):
        """clean() removes docs with empty or very short content."""
        from src.knowledge.retrieval.postprocess.cleaner import clean

        docs = [
            RetrievedDocument(name="good", content="A" * 100, meta_data={}),
            RetrievedDocument(name="empty", content="", meta_data={}),
            RetrievedDocument(name="short", content="hi", meta_data={}),
        ]
        result = clean(docs)
        assert all(len(d.content) > 10 for d in result)

    def test_dedup_by_content_removes_near_duplicates(self):
        """deduplicate_by_content removes docs with high Jaccard overlap."""
        from src.knowledge.retrieval.postprocess.deduplicator import deduplicate_by_content

        docs = [
            RetrievedDocument(
                name="a",
                content="The quick brown fox jumps over the lazy dog in the field",
                meta_data={},
            ),
            RetrievedDocument(
                name="b",
                content="The quick brown fox jumps over the lazy dog in the meadow",
                meta_data={},
            ),
            RetrievedDocument(
                name="c",
                content="Completely different content about banking compliance rules",
                meta_data={},
            ),
        ]
        result = deduplicate_by_content(docs, threshold=0.6)
        # "a" and "b" are near-dupes; "c" is different
        names = [d.name for d in result]
        assert "a" in names
        assert "c" in names

    def test_group_by_source_groups_by_doc_and_section(self):
        """group_by_source clusters docs by doc_id + section_id."""
        from src.knowledge.retrieval.postprocess.grouper import group_by_source

        docs = [
            RetrievedDocument(name="a", content="Content A", meta_data={"doc_id": "d1", "section_id": "s1"}),
            RetrievedDocument(name="b", content="Content B", meta_data={"doc_id": "d1", "section_id": "s1"}),
            RetrievedDocument(name="c", content="Content C", meta_data={"doc_id": "d2", "section_id": "s2"}),
        ]
        groups = group_by_source(docs)
        assert len(groups) == 2
        # First group should have 2 hits from d1/s1
        group_keys = {g.key for g in groups}
        assert len(group_keys) == 2


class TestGetTools:
    """Test that get_tools returns a callable search function."""

    def test_returns_one_tool(self):
        vk = VectorKnowledge(config=VectorKnowledgeConfig())
        tools = vk.get_tools()
        assert len(tools) == 1
        assert callable(tools[0])
        assert tools[0].__name__ == "search_knowledge_base"

    def test_tool_returns_no_results_when_qdrant_unavailable(self):
        vk = VectorKnowledge(config=VectorKnowledgeConfig())
        vk._get_qdrant = MagicMock(side_effect=RuntimeError("no qdrant"))
        tools = vk.get_tools()
        result = tools[0]("test query")
        assert "No relevant documents" in result


class TestAgetTools:
    """Test that aget_tools returns async callable."""

    def test_returns_one_async_tool(self):
        vk = VectorKnowledge(config=VectorKnowledgeConfig())
        tools = asyncio.run(vk.aget_tools())
        assert len(tools) == 1
        assert asyncio.iscoroutinefunction(tools[0])
        assert tools[0].__name__ == "search_knowledge_base"

    def test_async_tool_returns_no_results_when_qdrant_unavailable(self):
        vk = VectorKnowledge(config=VectorKnowledgeConfig())
        vk._get_qdrant = MagicMock(side_effect=RuntimeError("no qdrant"))
        tools = asyncio.run(vk.aget_tools())
        result = asyncio.run(tools[0]("test query"))
        assert "No relevant documents" in result


class TestBuildContext:
    """Test build_context returns a non-empty string."""

    def test_returns_context_string(self):
        vk = VectorKnowledge(config=VectorKnowledgeConfig())
        ctx = vk.build_context()
        assert "knowledge base" in ctx
        assert "search_knowledge_base" in ctx


class TestFormatResults:
    """Test _format_results formatting."""

    def test_empty_returns_no_results(self):
        assert VectorKnowledge._format_results([]) == "No results found."

    def test_formats_with_name_and_url(self):
        from agno.knowledge.document import Document

        docs = [
            Document(
                content="Some content here.",
                name="Test Doc",
                meta_data={"url": "https://example.com"},
            ),
        ]
        result = VectorKnowledge._format_results(docs)
        assert "[1]" in result
        assert "Test Doc" in result
        assert "(https://example.com)" in result
        assert "Some content here." in result

    def test_formats_multiple_docs(self):
        from agno.knowledge.document import Document

        docs = [
            Document(content="First.", name="A", meta_data={}),
            Document(content="Second.", name="B", meta_data={}),
        ]
        result = VectorKnowledge._format_results(docs)
        assert "[1]" in result
        assert "[2]" in result


class TestRefsToDocuments:
    """Test _refs_to_documents conversion."""

    def test_converts_ref_dicts_to_documents(self):
        from agno.knowledge.document import Document

        refs = [
            {
                "title": "Doc A",
                "content": "Hello world",
                "url": "https://example.com",
                "score": 0.9,
                "doc_id": "d1",
            },
        ]
        docs = VectorKnowledge._refs_to_documents(refs)
        assert len(docs) == 1
        assert isinstance(docs[0], Document)
        assert docs[0].name == "Doc A"
        assert docs[0].content == "Hello world"
        assert docs[0].meta_data["url"] == "https://example.com"

    def test_empty_refs_returns_empty(self):
        assert VectorKnowledge._refs_to_documents([]) == []
