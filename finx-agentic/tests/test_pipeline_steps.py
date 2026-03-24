"""Tests for the enhanced 6-step retrieval pipeline.

Covers each step independently and the full end-to-end flow.
All tests run without Qdrant or network — uses mock data only.

Run:  pytest tests/test_pipeline_steps.py -v
"""
from __future__ import annotations

import pytest

from src.core.models.retrieval import RetrievedDocument
from src.knowledge.retrieval.postprocess.cleaner import clean
from src.knowledge.retrieval.postprocess.deduplicator import deduplicate_by_content
from src.knowledge.retrieval.postprocess.grouper import (
    SourceGroup,
    flatten_groups,
    group_by_source,
)
from src.knowledge.retrieval.postprocess.expander import (
    ExpandedBlock,
    _group_to_block_passthrough,
    _merge_chunks_text,
)
from src.knowledge.retrieval.postprocess.reranker import rerank, rerank_blocks
from src.knowledge.retrieval.postprocess.context_packer import (
    blocks_to_documents,
    build_ref,
    pack_blocks,
    pack_refs,
)
from src.knowledge.retrieval.policy import DEFAULT_POLICY, POLICIES, get_policy


# ── Fixtures ─────────────────────────────────────────────────────────────


def _doc(
    name: str,
    content: str,
    doc_id: str = "d1",
    section_id: str = "s1",
    chunk_kind: str = "section",
    chunk_pos: int = 0,
    score: float = 0.8,
    source_url: str = "https://wiki.example.com/page1",
    **kw,
) -> RetrievedDocument:
    meta = {
        "doc_id": doc_id,
        "section_id": section_id,
        "chunk_kind": chunk_kind,
        "chunk_position": chunk_pos,
        "qdrant_score": score,
        "boosted_score": score,
        "source_url": source_url,
        "doc_title": name,
        "chunk_id": f"{doc_id}_{chunk_pos}",
        "heading": kw.pop("heading", ""),
        "heading_path": kw.pop("heading_path", []),
        "section_path": kw.pop("section_path", []),
        "mime_type": kw.pop("mime_type", ""),
        "content_type": kw.pop("content_type", ""),
        "attachment_id": kw.pop("attachment_id", ""),
        "doc_type": kw.pop("doc_type", ""),
        "source_type": kw.pop("source_type", ""),
        "language": kw.pop("language", ""),
        "space_key": kw.pop("space_key", ""),
        "domains": kw.pop("domains", []),
        "keywords": kw.pop("keywords", []),
        "quality_score": kw.pop("quality_score", 0.5),
        "total_chunks": kw.pop("total_chunks", 5),
        "parent_content_id": kw.pop("parent_content_id", ""),
        "table_headers": kw.pop("table_headers", []),
        "artifact_uri": kw.pop("artifact_uri", ""),
        "external_id": kw.pop("external_id", ""),
        **kw,
    }
    return RetrievedDocument(name=name, content=content, meta_data=meta)


@pytest.fixture
def raw_hits() -> list[RetrievedDocument]:
    """Simulates 10 raw hits from Step 1 — includes junk that Step 2 should drop."""
    return [
        # Good hits — Doc A (banking policy, 2 sections)
        _doc("Banking Policy Guide", "This document outlines the complete KYC verification process for new customers.",
             doc_id="d1", section_id="s1", chunk_pos=0, score=0.92,
             heading="KYC Overview", heading_path=["Banking Policy", "KYC Overview"]),
        _doc("Banking Policy Guide", "Step 1: Collect identity document. Step 2: Verify address. Step 3: Biometric check.",
             doc_id="d1", section_id="s1", chunk_pos=1, score=0.85,
             heading="KYC Steps", heading_path=["Banking Policy", "KYC Steps"]),
        _doc("Banking Policy Guide", "Anti-money laundering checks are mandatory for all accounts exceeding 10M VND.",
             doc_id="d1", section_id="s2", chunk_pos=2, score=0.78,
             heading="AML Rules", heading_path=["Banking Policy", "AML Rules"]),

        # Good hits — Doc B (compliance FAQ)
        _doc("Compliance FAQ", "Q: What documents are needed for KYC? A: National ID, proof of address, utility bill.",
             doc_id="d2", section_id="s3", chunk_pos=0, score=0.88,
             source_url="https://wiki.example.com/faq"),
        _doc("Compliance FAQ", "Q: How long does KYC take? A: Standard processing is 2-3 business days.",
             doc_id="d2", section_id="s3", chunk_pos=1, score=0.72,
             source_url="https://wiki.example.com/faq"),

        # Good hit — Doc C (table schema)
        _doc("Customer Table Schema", "Table: CUSTOMER_MASTER\nColumns: customer_id, full_name, kyc_status, kyc_date",
             doc_id="d3", section_id="s4", chunk_pos=0, score=0.80,
             chunk_kind="table_schema", table_headers=["customer_id", "full_name", "kyc_status"]),

        # ── JUNK below ──

        # Image without OCR text
        _doc("Diagram", "img", doc_id="d4", section_id="s5", chunk_pos=0,
             score=0.65, chunk_kind="image", mime_type="image/png"),

        # Too-short chunk
        _doc("Short", "OK", doc_id="d5", section_id="s6", chunk_pos=0, score=0.60),

        # Duplicate section title (same doc+section as first hit)
        _doc("Banking Policy Guide", "", doc_id="d1", section_id="s1",
             chunk_pos=99, score=0.50, chunk_kind="section_title"),

        # Zero-score chunk
        _doc("Orphan Node", "This chunk has content but was scored zero by vector search.",
             doc_id="d6", section_id="s7", chunk_pos=0, score=0.0),
    ]


# ═════════════════════════════════════════════════════════════════════════
# Step 2 — Cleaner
# ═════════════════════════════════════════════════════════════════════════


class TestStep2Cleaner:
    def test_drops_junk_keeps_good(self, raw_hits):
        result = clean(raw_hits)
        names = [d.name for d in result]

        # Should keep the 6 good hits
        assert len(result) == 6
        assert "Diagram" not in names          # image without text
        assert "Short" not in names            # too-short content
        assert "Orphan Node" not in names      # zero score

    def test_drops_empty_image(self):
        docs = [
            _doc("Fig", "x", chunk_kind="image", mime_type="image/png", score=0.5),
            _doc("Fig OCR", "This is OCR-extracted text from a scanned document with enough content.",
                 chunk_kind="image", mime_type="image/png", score=0.5),
        ]
        result = clean(docs)
        assert len(result) == 1
        assert result[0].name == "Fig OCR"

    def test_drops_short_content(self):
        docs = [
            _doc("A", "x" * 39, score=0.5),   # 39 chars — below threshold
            _doc("B", "x" * 40, score=0.5),   # 40 chars — exactly at threshold
        ]
        result = clean(docs)
        assert len(result) == 1
        assert result[0].name == "B"

    def test_drops_duplicate_section_titles(self):
        docs = [
            _doc("Title1", "A" * 50, doc_id="d1", section_id="s1",
                 chunk_kind="section_title", chunk_pos=0, score=0.8),
            _doc("Title2", "B" * 50, doc_id="d1", section_id="s1",
                 chunk_kind="section_title", chunk_pos=1, score=0.7),
            _doc("Regular", "C" * 50, doc_id="d1", section_id="s1",
                 chunk_kind="section", chunk_pos=2, score=0.6),
        ]
        result = clean(docs)
        # First section_title kept, second dropped, regular kept
        assert len(result) == 2
        assert result[0].name == "Title1"
        assert result[1].name == "Regular"

    def test_keeps_zero_score_when_flag_set(self):
        docs = [
            _doc("Zero", "A" * 50, score=0.0),
        ]
        assert len(clean(docs)) == 0
        assert len(clean(docs, keep_zero_score=True)) == 1

    def test_empty_input(self):
        assert clean([]) == []


# ═════════════════════════════════════════════════════════════════════════
# Step 3 — Grouper
# ═════════════════════════════════════════════════════════════════════════


class TestStep3Grouper:
    def test_groups_by_doc_section(self, raw_hits):
        cleaned = clean(raw_hits)
        groups = group_by_source(cleaned)

        # d1/s1 (2 hits), d1/s2 (1 hit), d2/s3 (2 hits), d3/s4 table (1 hit)
        assert len(groups) == 4

    def test_group_sorted_by_best_score(self, raw_hits):
        cleaned = clean(raw_hits)
        groups = group_by_source(cleaned)

        scores = [g.best_score for g in groups]
        assert scores == sorted(scores, reverse=True), "Groups should be sorted by descending best_score"

    def test_table_chunks_group_separately(self):
        docs = [
            _doc("T1", "A" * 50, doc_id="d1", section_id="s1",
                 chunk_kind="table_schema", chunk_pos=0, score=0.8),
            _doc("T1", "B" * 50, doc_id="d1", section_id="s1",
                 chunk_kind="table_row_group", chunk_pos=1, score=0.7),
            _doc("T1", "C" * 50, doc_id="d1", section_id="s1",
                 chunk_kind="section", chunk_pos=2, score=0.6),
        ]
        groups = group_by_source(docs)
        keys = [g.key for g in groups]

        # Table chunks grouped under table:: prefix, regular under section::
        assert any(k.startswith("table::") for k in keys)
        assert any(k.startswith("section::") for k in keys)

    def test_attachment_groups_separately(self):
        docs = [
            _doc("A", "X" * 50, doc_id="d1", section_id="s1",
                 attachment_id="att1", chunk_pos=0, score=0.8),
            _doc("A", "Y" * 50, doc_id="d1", section_id="s1",
                 chunk_pos=1, score=0.7),
        ]
        groups = group_by_source(docs)
        keys = [g.key for g in groups]
        assert any(k.startswith("file::") for k in keys)
        assert any(k.startswith("section::") for k in keys)

    def test_max_groups_cap(self):
        docs = [
            _doc(f"D{i}", "X" * 50, doc_id=f"d{i}", section_id=f"s{i}",
                 chunk_pos=0, score=0.5 + i * 0.01)
            for i in range(20)
        ]
        groups = group_by_source(docs, max_groups=5)
        assert len(groups) == 5

    def test_flatten_preserves_order(self):
        docs = [
            _doc("A", "X" * 50, chunk_pos=2, score=0.9),
            _doc("A", "Y" * 50, chunk_pos=0, score=0.8),
            _doc("A", "Z" * 50, chunk_pos=1, score=0.7),
        ]
        groups = group_by_source(docs)
        flat = flatten_groups(groups)
        positions = [d.meta_data["chunk_position"] for d in flat]
        assert positions == sorted(positions), "Flattened docs should be ordered by chunk_position"

    def test_best_hit_and_best_score(self):
        docs = [
            _doc("A", "X" * 50, chunk_pos=0, score=0.6),
            _doc("A", "Y" * 50, chunk_pos=1, score=0.9),
        ]
        groups = group_by_source(docs)
        assert len(groups) == 1
        assert groups[0].best_score == 0.9
        assert groups[0].best_hit.meta_data["chunk_position"] == 1

    def test_empty_input(self):
        assert group_by_source([]) == []


# ═════════════════════════════════════════════════════════════════════════
# Step 4 — Expander (passthrough, no Qdrant)
# ═════════════════════════════════════════════════════════════════════════


class TestStep4Expander:
    def test_passthrough_preserves_chunks(self):
        docs = [
            _doc("A", "First chunk content here", chunk_pos=0, score=0.9),
            _doc("A", "Second chunk content here", chunk_pos=1, score=0.8),
        ]
        groups = group_by_source(docs)
        block = _group_to_block_passthrough(groups[0])

        assert isinstance(block, ExpandedBlock)
        assert len(block.chunks) == 2
        assert block.doc_id == "d1"
        assert block.source_label != ""

    def test_passthrough_orders_by_position(self):
        docs = [
            _doc("A", "Second" + "x" * 40, chunk_pos=2, score=0.7),
            _doc("A", "First" + "y" * 40, chunk_pos=0, score=0.9),
        ]
        groups = group_by_source(docs)
        block = _group_to_block_passthrough(groups[0])

        positions = [c.meta_data["chunk_position"] for c in block.chunks]
        assert positions == [0, 2]

    def test_block_content_includes_source_metadata(self):
        docs = [
            _doc("My Doc Title", "Important banking regulation content for compliance",
                 source_url="https://wiki.example.com/doc1", chunk_pos=0, score=0.9,
                 heading_path=["Policies", "Banking"],
                 section_path=["Page: Root", "Section: Regulations"]),
        ]
        groups = group_by_source(docs)
        block = _group_to_block_passthrough(groups[0])

        assert "My Doc Title" in block.content
        assert "https://wiki.example.com/doc1" in block.content
        assert "Regulations" in block.content  # section breadcrumb

    def test_block_as_document(self):
        docs = [
            _doc("A", "Content" + "x" * 40, chunk_pos=0, score=0.9),
        ]
        groups = group_by_source(docs)
        block = _group_to_block_passthrough(groups[0])
        doc = block.as_document()

        assert isinstance(doc, RetrievedDocument)
        assert doc.content == block.content
        assert doc.meta_data["block_chunk_count"] == 1
        assert doc.meta_data["block_source_label"] == block.source_label

    def test_merge_deduplicates_chunk_text(self):
        docs = [
            _doc("A", "Same content repeated exactly", chunk_pos=0, score=0.9),
            _doc("A", "Same content repeated exactly", chunk_pos=1, score=0.8),
        ]
        groups = group_by_source(docs)
        block = _group_to_block_passthrough(groups[0])

        # Content should appear only once (deduped)
        count = block.content.count("Same content repeated exactly")
        assert count == 1


# ═════════════════════════════════════════════════════════════════════════
# Step 5 — Reranker
# ═════════════════════════════════════════════════════════════════════════


class TestStep5Reranker:
    def test_rerank_blocks_fallback_sorts_by_score(self):
        """Without a CrossEncoder model loaded, should fall back to score ordering."""
        blocks = [
            ExpandedBlock(source_label="Low", source_url="", doc_id="d1",
                          section_id="s1", content="Low score block", chunks=[], best_hit_score=0.3),
            ExpandedBlock(source_label="High", source_url="", doc_id="d2",
                          section_id="s2", content="High score block", chunks=[], best_hit_score=0.95),
            ExpandedBlock(source_label="Mid", source_url="", doc_id="d3",
                          section_id="s3", content="Mid score block", chunks=[], best_hit_score=0.6),
        ]
        ranked = rerank_blocks("KYC process", blocks, top_n=6)

        assert len(ranked) == 3
        assert ranked[0].source_label == "High"
        assert ranked[1].source_label == "Mid"
        assert ranked[2].source_label == "Low"

    def test_rerank_blocks_respects_top_n(self):
        blocks = [
            ExpandedBlock(source_label=f"B{i}", source_url="", doc_id=f"d{i}",
                          section_id="s", content=f"Block {i}", chunks=[], best_hit_score=0.5 + i * 0.05)
            for i in range(10)
        ]
        ranked = rerank_blocks("query", blocks, top_n=3)
        assert len(ranked) == 3

    def test_rerank_blocks_empty(self):
        assert rerank_blocks("query", [], top_n=6) == []

    def test_rerank_docs_fallback_sorts_by_boosted_score(self):
        docs = [
            _doc("A", "Low score", score=0.3),
            _doc("B", "High score", score=0.9),
        ]
        ranked = rerank(
            "query", docs, top_n=5,
        )
        assert ranked[0].name == "B"
        assert "rerank_score" in ranked[0].meta_data


# ═════════════════════════════════════════════════════════════════════════
# Step 6 — Packer
# ═════════════════════════════════════════════════════════════════════════


class TestStep6Packer:
    def _make_block(self, label, content, score=0.8, doc_id="d1", section_id="s1", url=""):
        chunk = _doc(label, content, doc_id=doc_id, section_id=section_id, score=score)
        return ExpandedBlock(
            source_label=label, source_url=url, doc_id=doc_id,
            section_id=section_id, content=content,
            chunks=[chunk], best_hit_score=score,
        )

    def test_pack_blocks_respects_max(self):
        blocks = [self._make_block(f"B{i}", f"Content {i}" * 10, score=0.9 - i * 0.1)
                   for i in range(10)]
        packed = pack_blocks(blocks, max_blocks=4)
        assert len(packed) <= 4

    def test_pack_blocks_output_structure(self):
        blocks = [self._make_block("Block A", "Some important content about KYC",
                                    score=0.9, url="https://wiki.example.com/a")]
        packed = pack_blocks(blocks)
        assert len(packed) == 1

        ref = packed[0]
        assert ref["ref"] == 1
        assert ref["title"] == "Block A"
        assert "content" in ref
        assert ref["url"] == "https://wiki.example.com/a"
        assert ref["score"] == 0.9
        assert ref["chunk_count"] == 1

    def test_pack_blocks_respects_char_budget(self):
        blocks = [self._make_block(f"B{i}", "x" * 5000, score=0.9 - i * 0.05)
                   for i in range(8)]
        # min_blocks=3 means the budget won't stop packing until at least 3 blocks.
        # After min_blocks is reached, the budget kicks in.
        packed = pack_blocks(blocks, max_blocks=8, min_blocks=1, max_total_chars=10000)

        total_chars = sum(len(r["content"]) for r in packed)
        assert total_chars <= 10000

    def test_pack_blocks_min_blocks_overrides_budget(self):
        """min_blocks guarantees at least N blocks even if budget is exceeded."""
        blocks = [self._make_block(f"B{i}", "x" * 5000, score=0.9 - i * 0.05)
                   for i in range(8)]
        packed = pack_blocks(blocks, max_blocks=8, min_blocks=3, max_total_chars=10000)
        assert len(packed) >= 3

    def test_pack_blocks_empty(self):
        assert pack_blocks([]) == []

    def test_blocks_to_documents(self):
        blocks = [self._make_block("A", "Content A"), self._make_block("B", "Content B", doc_id="d2")]
        docs = blocks_to_documents(blocks)

        assert len(docs) == 2
        assert all(isinstance(d, RetrievedDocument) for d in docs)
        assert docs[0].meta_data["block_source_label"] == "A"

    def test_pack_refs_legacy_still_works(self):
        docs = [
            _doc("A", "Content about KYC verification" * 5, score=0.9,
                 **{"rerank_score": 0.9}),
            _doc("B", "Content about AML rules and checks" * 5, score=0.8,
                 doc_id="d2", **{"rerank_score": 0.8}),
        ]
        refs = pack_refs(docs, max_refs=5, max_total_chars=10000)
        assert 1 <= len(refs) <= 5
        assert refs[0]["ref"] == 1


# ═════════════════════════════════════════════════════════════════════════
# Policy
# ═════════════════════════════════════════════════════════════════════════


class TestPolicy:
    def test_default_targets_3_to_6_blocks(self):
        assert 3 <= DEFAULT_POLICY.max_refs <= 6

    def test_all_policies_have_sane_max_refs(self):
        for name, policy in POLICIES.items():
            if policy.skip_retrieval:
                continue
            assert 1 <= policy.max_refs <= 10, f"Policy {name} max_refs={policy.max_refs} out of range"
            assert policy.top_k >= policy.rerank_top_n, (
                f"Policy {name}: top_k={policy.top_k} < rerank_top_n={policy.rerank_top_n}"
            )

    def test_get_policy_fallback(self):
        p = get_policy("nonexistent_type")
        assert p == DEFAULT_POLICY


# ═════════════════════════════════════════════════════════════════════════
# End-to-end: Steps 2 → 6
# ═════════════════════════════════════════════════════════════════════════


class TestEndToEnd:
    def test_full_pipeline_steps(self, raw_hits):
        """Simulate Steps 2–6 without Qdrant (uses passthrough expansion)."""
        query = "KYC verification process"

        # Step 1: raw_hits already provided (10 hits)
        assert len(raw_hits) == 10

        # Step 2: Clean
        cleaned = clean(raw_hits)
        assert 4 <= len(cleaned) <= 8
        # Verify junk was dropped
        junk_names = {"Diagram", "Short", "Orphan Node"}
        assert not junk_names & {d.name for d in cleaned}

        # Content dedup
        deduped = deduplicate_by_content(cleaned)
        assert len(deduped) <= len(cleaned)

        # Step 3: Group
        groups = group_by_source(deduped)
        assert 1 <= len(groups) <= 10
        # Verify score ordering
        scores = [g.best_score for g in groups]
        assert scores == sorted(scores, reverse=True)

        # Step 4: Expand (passthrough)
        blocks = [_group_to_block_passthrough(g) for g in groups]
        assert len(blocks) == len(groups)
        for b in blocks:
            assert b.content  # non-empty
            assert b.source_label

        # Step 5: Rerank
        ranked = rerank_blocks(query, blocks, top_n=6)
        assert 1 <= len(ranked) <= 6

        # Step 6: Pack
        packed = pack_blocks(ranked, max_blocks=6, max_total_chars=16000)
        assert 1 <= len(packed) <= 6

        # Verify output structure
        for ref in packed:
            assert "ref" in ref
            assert "title" in ref
            assert "content" in ref
            assert len(ref["content"]) > 0

        # Verify citation docs
        final_docs = blocks_to_documents(ranked)
        assert len(final_docs) == len(ranked)

    def test_all_junk_input_returns_empty(self):
        """If all hits are junk, pipeline should produce 0 results gracefully."""
        docs = [
            _doc("Img", "x", chunk_kind="image", mime_type="image/png", score=0.5),
            _doc("Short", "hi", score=0.5),
        ]
        cleaned = clean(docs)
        assert cleaned == []
        groups = group_by_source(cleaned)
        assert groups == []
        blocks = [_group_to_block_passthrough(g) for g in groups]
        assert blocks == []
        packed = pack_blocks(blocks)
        assert packed == []

    def test_single_good_hit_flows_through(self):
        docs = [
            _doc("Solo", "This is the only good chunk and it has enough content for the pipeline.",
                 doc_id="d1", section_id="s1", chunk_pos=0, score=0.9),
        ]
        cleaned = clean(docs)
        assert len(cleaned) == 1

        groups = group_by_source(cleaned)
        assert len(groups) == 1

        blocks = [_group_to_block_passthrough(g) for g in groups]
        assert len(blocks) == 1
        assert blocks[0].source_label != ""

        ranked = rerank_blocks("test query", blocks, top_n=6)
        assert len(ranked) == 1

        packed = pack_blocks(ranked, max_blocks=6)
        assert len(packed) == 1
        assert packed[0]["ref"] == 1

    def test_many_docs_diverse_sources(self):
        """Pipeline should handle hits from many different documents."""
        docs = [
            _doc(f"Doc {i}", f"Content for document {i} with enough text for the pipeline to keep it.",
                 doc_id=f"d{i}", section_id=f"s{i}", chunk_pos=0, score=0.9 - i * 0.05)
            for i in range(15)
        ]
        cleaned = clean(docs)
        groups = group_by_source(cleaned, max_groups=8)
        blocks = [_group_to_block_passthrough(g) for g in groups]
        ranked = rerank_blocks("general query", blocks, top_n=6)
        packed = pack_blocks(ranked, max_blocks=6)

        assert 1 <= len(packed) <= 6
