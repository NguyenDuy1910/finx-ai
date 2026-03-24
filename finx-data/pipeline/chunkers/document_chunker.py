"""Document chunker: PDF/DOCX/PPTX via section_hierarchy."""

from __future__ import annotations

from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.chunk import ChunkDocument, ChunkKind
from pipeline.chunkers.base import BaseChunker
from pipeline.chunkers.table_chunker import TableChunker
from pipeline.schemas.blocks import BlockType


class DocumentChunker(BaseChunker):
    """Chunks documents (PDF/DOCX/PPTX) using section_hierarchy.

    Strategy:
    - INTRO chunk: Text before first heading
    - SECTION chunks: One per SectionNode, split at sentence boundaries if > MAX_TOKENS
    - TableBlock instances → delegated to TableChunker

    Works best with DoclingExtractor output (which builds section_hierarchy).
    Falls back to sliding window if no section hierarchy present.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize DocumentChunker with TableChunker as delegate."""
        super().__init__(*args, **kwargs)
        self.table_chunker = TableChunker(*args, **kwargs)

    def chunk(
        self,
        doc: CanonicalDocument,
        *,
        tenant_id: str | None = None,
        acl_readers: list[str] | None = None,
        acl_spaces: list[str] | None = None,
        is_public: bool = False,
    ) -> list[ChunkDocument]:
        """Chunk a document.

        Args:
            doc: CanonicalDocument (typically from DoclingExtractor)
            tenant_id: Tenant override
            acl_readers: Readers list
            acl_spaces: Spaces list
            is_public: Public flag

        Returns:
            List of ChunkDocuments
        """
        chunks = []
        chunk_position = 0

        base_chunk = self._base_chunk_doc(
            doc,
            tenant_id=tenant_id,
            acl_readers=acl_readers,
            acl_spaces=acl_spaces,
            is_public=is_public,
        )

        # If section_hierarchy exists, use it; otherwise fall back to sliding window
        if doc.section_hierarchy:
            intro_text = self._extract_intro_text(doc)
            if intro_text and self._word_count(intro_text) >= self.MIN_CHUNK_WORDS:
                chunk = ChunkDocument(
                    chunk_kind=ChunkKind.INTRO,
                    heading="",
                    heading_path=[],
                    chunk_text=intro_text,
                    display_text=intro_text,
                    chunk_position=chunk_position,
                    total_chunks=0,  # Will update later
                    **base_chunk,
                )
                chunks.append(chunk)
                chunk_position += 1

            # Process sections
            for section_node in doc.section_hierarchy:
                section_chunks = self._chunk_section(
                    section_node,
                    doc,
                    base_chunk,
                    chunk_position,
                )
                chunks.extend(section_chunks)
                chunk_position += len(section_chunks)
        else:
            # No section hierarchy: sliding window over full text
            full_text = doc.full_text()
            if full_text:
                text_chunks = self._split_text_with_overlap(
                    full_text,
                    self.MAX_TOKENS,
                    self.OVERLAP_TOKENS,
                )
                for text_chunk in text_chunks:
                    chunk = ChunkDocument(
                        chunk_kind=ChunkKind.SECTION,
                        heading="",
                        heading_path=[],
                        chunk_text=text_chunk,
                        display_text=text_chunk,
                        chunk_position=chunk_position,
                        total_chunks=0,  # Will update later
                        **base_chunk,
                    )
                    chunks.append(chunk)
                    chunk_position += 1

        # Update total_chunks
        total = len(chunks)
        for chunk in chunks:
            chunk.total_chunks = total

        return chunks

    def _extract_intro_text(self, doc: CanonicalDocument) -> str:
        """Extract text blocks before the first heading."""
        intro_blocks = []

        for block in doc.content_blocks:
            # Stop at first heading
            if hasattr(block, "block_type") and block.block_type.value == "heading":
                break

            if hasattr(block, "block_type"):
                block_type = block.block_type.value
                if block_type == "text":
                    intro_blocks.append(block.content)
                elif block_type == "code":
                    intro_blocks.append(f"```{block.language or ''}\n{block.content}\n```")
                elif block_type == "list":
                    intro_blocks.append(
                        "\n".join(f"- {item}" for item in block.items)
                    )

        return "\n\n".join(intro_blocks).strip()

    def _chunk_section(
        self,
        section_node,
        doc: CanonicalDocument,
        base_chunk: dict,
        position_offset: int,
    ) -> list[ChunkDocument]:
        """Chunk one section recursively, delegating tables/kv/chart/diagram to specialized handlers."""
        chunks = []
        position = position_offset

        # Separate text blocks from structured blocks
        text_blocks = []
        table_blocks = []
        kv_blocks = []
        chart_blocks = []
        diagram_blocks = []

        for block_idx in section_node.block_indices:
            if block_idx < len(doc.content_blocks):
                block = doc.content_blocks[block_idx]

                if hasattr(block, "block_type"):
                    bt = block.block_type
                    if bt == BlockType.TABLE:
                        table_blocks.append((block_idx, block))
                    elif bt == BlockType.KEY_VALUE:
                        kv_blocks.append(block)
                    elif bt == BlockType.CHART:
                        chart_blocks.append(block)
                    elif bt == BlockType.DIAGRAM:
                        diagram_blocks.append(block)
                    else:
                        text_blocks.append(block)

        # Process text blocks as section text
        section_text = self._build_section_text(text_blocks)

        if section_text and self._word_count(section_text) >= self.MIN_CHUNK_WORDS:
            text_chunks = self._split_text_with_overlap(
                section_text,
                self.MAX_TOKENS,
                self.OVERLAP_TOKENS,
            )

            for i, text_chunk in enumerate(text_chunks):
                chunk = ChunkDocument(
                    chunk_kind=ChunkKind.SECTION,
                    heading=section_node.title,
                    heading_path=section_node.path,
                    chunk_text=self._make_chunk_text(section_node.title, text_chunk),
                    display_text=text_chunk,
                    chunk_position=position,
                    total_chunks=0,
                    **base_chunk,
                )
                chunks.append(chunk)
                position += 1

        # Process tables
        for _, table_block in table_blocks:
            table_chunks = self.table_chunker.chunk_table_block(
                table_block,
                context={
                    "doc": doc,
                    "section_node": section_node,
                    "base_chunk": base_chunk,
                    "position_offset": position,
                },
            )
            chunks.extend(table_chunks)
            position += len(table_chunks)

        # Process key-value blocks
        for kv_block in kv_blocks:
            kv_text = "\n".join(
                f"{p.get('key', '')}: {p.get('value', '')}" for p in kv_block.pairs if p.get("key")
            )
            if kv_text and self._word_count(kv_text) >= self.MIN_CHUNK_WORDS:
                chunks.append(ChunkDocument(
                    chunk_kind=ChunkKind.KEY_VALUE,
                    heading=section_node.title,
                    heading_path=section_node.path,
                    chunk_text=self._make_chunk_text(section_node.title, kv_text),
                    display_text=kv_text,
                    content_type="key_value",
                    chunk_position=position,
                    total_chunks=0,
                    **base_chunk,
                ))
                position += 1

        # Process chart blocks
        for chart_block in chart_blocks:
            parts = []
            if chart_block.title:
                parts.append(f"Chart: {chart_block.title}")
            if chart_block.trend_summary:
                parts.append(chart_block.trend_summary)
            if chart_block.description:
                parts.append(chart_block.description)
            chart_text = "\n".join(parts)
            if chart_text and self._word_count(chart_text) >= self.MIN_CHUNK_WORDS:
                chunks.append(ChunkDocument(
                    chunk_kind=ChunkKind.CHART_SUMMARY,
                    heading=chart_block.title or section_node.title,
                    heading_path=section_node.path,
                    chunk_text=self._make_chunk_text(section_node.title, chart_text),
                    display_text=chart_text,
                    content_type="chart",
                    chunk_position=position,
                    total_chunks=0,
                    **base_chunk,
                ))
                position += 1

        # Process diagram blocks
        for diagram_block in diagram_blocks:
            parts = []
            if diagram_block.title:
                parts.append(f"Diagram: {diagram_block.title}")
            if diagram_block.description:
                parts.append(diagram_block.description)
            if diagram_block.components:
                parts.append(f"Components: {', '.join(diagram_block.components)}")
            if diagram_block.relationships:
                parts.append("Relationships:\n" + "\n".join(f"  {r}" for r in diagram_block.relationships))
            diagram_text = "\n".join(parts)
            if diagram_text and self._word_count(diagram_text) >= self.MIN_CHUNK_WORDS:
                chunks.append(ChunkDocument(
                    chunk_kind=ChunkKind.DIAGRAM_SUMMARY,
                    heading=diagram_block.title or section_node.title,
                    heading_path=section_node.path,
                    chunk_text=self._make_chunk_text(section_node.title, diagram_text),
                    display_text=diagram_text,
                    content_type="diagram",
                    chunk_position=position,
                    total_chunks=0,
                    **base_chunk,
                ))
                position += 1

        # Process child sections
        for child in section_node.children:
            child_chunks = self._chunk_section(child, doc, base_chunk, position)
            chunks.extend(child_chunks)
            position += len(child_chunks)

        return chunks

    def _build_section_text(self, blocks: list) -> str:
        """Build text from a list of content blocks."""
        result = []

        for block in blocks:
            if hasattr(block, "block_type"):
                block_type = block.block_type.value

                if block_type == "text":
                    result.append(block.content)
                elif block_type == "code":
                    result.append(f"```{block.language or ''}\n{block.content}\n```")
                elif block_type == "list":
                    result.append("\n".join(f"- {item}" for item in block.items))
                elif block_type == "image":
                    caption = block.description or block.alt_text or ""
                    if caption:
                        result.append(f"[Image: {caption}]")
                elif block_type == "key_value":
                    lines = [f"{p.get('key', '')}: {p.get('value', '')}" for p in block.pairs if p.get("key")]
                    if lines:
                        result.append("\n".join(lines))
                elif block_type == "chart":
                    parts = []
                    if block.title:
                        parts.append(f"Chart: {block.title}")
                    if block.trend_summary:
                        parts.append(block.trend_summary)
                    elif block.description:
                        parts.append(block.description)
                    if parts:
                        result.append("\n".join(parts))
                elif block_type == "diagram":
                    parts = []
                    if block.title:
                        parts.append(f"Diagram: {block.title}")
                    if block.description:
                        parts.append(block.description)
                    if parts:
                        result.append("\n".join(parts))

        return "\n\n".join(result).strip()
