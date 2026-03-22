"""Excel/CSV chunker: schema summary + row-group chunks."""

from __future__ import annotations

from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.chunk import ChunkDocument, ChunkKind
from pipeline.chunkers.base import BaseChunker
from pipeline.chunkers.table_chunker import TableChunker


class ExcelChunker(BaseChunker):
    """Chunks Excel/CSV files into structured metadata chunks.

    Strategy:
    - SCHEMA_SUMMARY: Column names, types, row count (metadata summary)
    - TABLE_ROW_GROUP: Row batches (50 rows per chunk for CSV/Excel)

    Delegates to TableChunker for row-group logic.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize ExcelChunker with larger row_group_size for CSV/Excel."""
        super().__init__(*args, **kwargs)
        # Larger batch size for CSV/Excel (vs 20 for embedded tables)
        self.table_chunker = TableChunker(*args, row_group_size=50, **kwargs)

    def chunk(
        self,
        doc: CanonicalDocument,
        *,
        tenant_id: str | None = None,
        acl_readers: list[str] | None = None,
        acl_spaces: list[str] | None = None,
        is_public: bool = False,
    ) -> list[ChunkDocument]:
        """Chunk an Excel/CSV CanonicalDocument.

        Args:
            doc: CanonicalDocument from Excel/CSV file
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

        # Extract metadata from doc.metadata
        columns = doc.metadata.get("columns", [])
        row_count = doc.metadata.get("row_count", 0)

        # Chunk 1: SCHEMA_SUMMARY
        if columns:
            schema_text = self._build_schema_text(doc.title, columns, row_count)
            chunk = ChunkDocument(
                chunk_kind=ChunkKind.SCHEMA_SUMMARY,
                heading=f"File Schema: {doc.title}",
                heading_path=[],
                chunk_text=schema_text,
                display_text=schema_text,
                chunk_position=chunk_position,
                total_chunks=0,  # Will update
                table_headers=[c.get("name", f"col_{i}") for i, c in enumerate(columns)],
                table_row_count=row_count,
                **base_chunk,
            )
            chunks.append(chunk)
            chunk_position += 1

        # Chunk 2+: Row groups from TableBlock if present
        seen_texts: set[str] = set()
        for block in doc.content_blocks:
            if hasattr(block, "block_type") and block.block_type.value == "table":
                table_chunks = self.table_chunker.chunk_table_block(
                    block,
                    context={
                        "doc": doc,
                        "base_chunk": base_chunk,
                        "position_offset": chunk_position,
                    },
                )
                # Deduplicate identical chunk text within this document
                for tc in table_chunks:
                    if tc.chunk_text not in seen_texts:
                        seen_texts.add(tc.chunk_text)
                        tc.chunk_position = chunk_position
                        chunks.append(tc)
                        chunk_position += 1

        # Update total_chunks
        total = len(chunks)
        for chunk in chunks:
            chunk.total_chunks = total

        return chunks

    def _build_schema_text(
        self,
        filename: str,
        columns: list[dict],
        row_count: int,
    ) -> str:
        """Build SCHEMA_SUMMARY chunk text."""
        lines = [f"File: {filename}"]
        lines.append(f"Columns ({len(columns)}):")

        for col in columns:
            name = col.get("name", "?")
            data_type = col.get("data_type", "unknown")
            description = col.get("description", "")
            lines.append(f"  • {name} ({data_type})" + (f" - {description}" if description else ""))

        lines.append(f"Total rows: {row_count}")

        # Add sample first row if available
        if row_count > 0:
            lines.append("Sample (first row):")
            for col in columns:
                name = col.get("name", "?")
                lines.append(f"  {name}: [data]")

        return "\n".join(lines)
