"""Table chunker: produces TABLE_SCHEMA, TABLE_ROW_GROUP, TABLE_SUMMARY chunks."""

from __future__ import annotations

from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.chunk import ChunkDocument, ChunkKind
from pipeline.chunkers.base import BaseChunker


class TableChunker(BaseChunker):
    """Chunks table data into structured summaries.

    Strategy:
    - TABLE_SCHEMA: Column headers + types (for metadata-aware retrieval)
    - TABLE_ROW_GROUP: Batches of up to ROW_GROUP_SIZE rows with summary
    - TABLE_SUMMARY: For small tables (≤ ROW_GROUP_SIZE rows)

    Two entry points:
    - chunk(doc): standalone table documents
    - chunk_table_block(block, context): called by other chunkers mid-document

    ROW_GROUP_SIZE = 20 (for embedded tables in documents)
    ROW_GROUP_SIZE = 50 (for Excel files, delegated from ExcelChunker)
    """

    def __init__(self, *args, row_group_size: int = 20, **kwargs) -> None:
        """Initialize TableChunker.

        Args:
            row_group_size: Number of rows per chunk. Default 20 for embedded tables.
        """
        super().__init__(*args, **kwargs)
        self.row_group_size = row_group_size

    def chunk(
        self,
        doc: CanonicalDocument,
        *,
        tenant_id: str | None = None,
        acl_readers: list[str] | None = None,
        acl_spaces: list[str] | None = None,
        is_public: bool = False,
    ) -> list[ChunkDocument]:
        """Chunk a table-only document (e.g., Athena schema).

        Args:
            doc: CanonicalDocument (table document)
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

        # Find table blocks in content_blocks
        for block in doc.content_blocks:
            if hasattr(block, "block_type") and block.block_type.value == "table":
                table_chunks = self.chunk_table_block(
                    block,
                    context={
                        "doc": doc,
                        "base_chunk": base_chunk,
                        "position_offset": chunk_position,
                    },
                )
                chunks.extend(table_chunks)
                chunk_position += len(table_chunks)

        # Update total_chunks
        total = len(chunks)
        for chunk in chunks:
            chunk.total_chunks = total

        return chunks

    def chunk_table_block(
        self,
        table_block,
        *,
        context: dict,
    ) -> list[ChunkDocument]:
        """Chunk a single TableBlock.

        Called by DocumentChunker and ExcelChunker as a sub-chunker.

        Args:
            table_block: TableBlock instance
            context: Dict with:
                - doc: parent CanonicalDocument
                - base_chunk: base chunk fields dict
                - position_offset: starting chunk position

        Returns:
            List of ChunkDocuments for this table
        """
        chunks = []
        doc = context.get("doc")
        base_chunk = context.get("base_chunk", {})
        position_offset = context.get("position_offset", 0)

        if not hasattr(table_block, "headers") or not table_block.headers:
            return []  # Empty table, skip

        caption = table_block.caption or doc.title if doc else ""
        headers = table_block.headers
        rows = table_block.rows

        # Skip trivial tables: single column with no rows and a
        # non-meaningful header (just a number or short value).
        if len(headers) <= 1 and len(rows) == 0:
            header_val = headers[0].strip() if headers else ""
            # Skip if header is empty, numeric, or very short (< 4 chars)
            if not header_val or len(header_val) < 4:
                return []
            # Skip if header is purely numeric (cell value treated as header)
            try:
                float(header_val.replace(",", ""))
                return []
            except ValueError:
                pass

        # Chunk 1: TABLE_SCHEMA (always)
        schema_text = self._build_schema_text(caption, headers)
        if schema_text:
            chunk = ChunkDocument(
                chunk_kind=ChunkKind.TABLE_SCHEMA,
                heading=f"Table Schema: {caption}",
                heading_path=[],
                chunk_text=schema_text,
                display_text=schema_text,
                chunk_position=position_offset,
                total_chunks=0,  # Will update
                table_headers=headers,
                table_row_count=len(rows),
                **base_chunk,
            )
            chunks.append(chunk)

        # Chunk 2+: TABLE_ROW_GROUP or TABLE_SUMMARY
        if len(rows) > self.row_group_size:
            # Large table: chunk by row groups
            for i in range(0, len(rows), self.row_group_size):
                row_batch = rows[i : i + self.row_group_size]
                row_group_text = self._build_row_group_text(
                    caption, headers, row_batch, i, len(rows)
                )
                chunk = ChunkDocument(
                    chunk_kind=ChunkKind.TABLE_ROW_GROUP,
                    heading=f"{caption} (rows {i + 1}-{min(i + self.row_group_size, len(rows))})",
                    heading_path=[],
                    chunk_text=row_group_text,
                    display_text=row_group_text,
                    chunk_position=position_offset + len(chunks),
                    total_chunks=0,  # Will update
                    table_headers=headers,
                    table_row_count=len(rows),
                    **base_chunk,
                )
                chunks.append(chunk)
        else:
            # Small table: one TABLE_SUMMARY chunk with all rows
            summary_text = self._build_summary_text(caption, headers, rows)
            chunk = ChunkDocument(
                chunk_kind=ChunkKind.TABLE_SUMMARY,
                heading=f"Table: {caption}",
                heading_path=[],
                chunk_text=summary_text,
                display_text=summary_text,
                chunk_position=position_offset + 1,  # After schema
                total_chunks=0,  # Will update
                table_headers=headers,
                table_row_count=len(rows),
                **base_chunk,
            )
            chunks.append(chunk)

        return chunks

    def _build_schema_text(self, caption: str, headers: list[str]) -> str:
        """Build TABLE_SCHEMA chunk text."""
        lines = [f"Table: {caption}"]
        lines.append(f"Columns ({len(headers)}): {', '.join(headers)}")
        return "\n".join(lines)

    def _build_row_group_text(
        self,
        caption: str,
        headers: list[str],
        rows: list[list[str]],
        row_start: int,
        total_rows: int,
    ) -> str:
        """Build TABLE_ROW_GROUP chunk text."""
        lines = [f"Table: {caption}"]
        lines.append(f"Rows {row_start + 1}–{min(row_start + len(rows), total_rows)} of {total_rows}")
        lines.append(f"Columns: {', '.join(headers)}")
        lines.append("")

        for row_idx, row in enumerate(rows):
            lines.append(f"Row {row_start + row_idx + 1}:")
            for header, value in zip(headers, row):
                lines.append(f"  {header}: {value}")
            lines.append("")

        return "\n".join(lines).strip()

    def _build_summary_text(
        self,
        caption: str,
        headers: list[str],
        rows: list[list[str]],
    ) -> str:
        """Build TABLE_SUMMARY chunk text (small tables)."""
        lines = [f"Table: {caption}"]
        lines.append(f"Columns ({len(headers)}): {', '.join(headers)}")
        lines.append(f"Total rows: {len(rows)}")
        lines.append("")

        for row_idx, row in enumerate(rows):
            lines.append(f"Row {row_idx + 1}:")
            for header, value in zip(headers, row):
                lines.append(f"  {header}: {value}")
            lines.append("")

        return "\n".join(lines).strip()
