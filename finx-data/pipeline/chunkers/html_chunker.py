"""HTML chunker: fallback for non-Confluence HTML sources."""

from __future__ import annotations

from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.chunk import ChunkDocument, ChunkKind
from pipeline.chunkers.confluence_chunker import ConfluenceChunker


class HTMLChunker(ConfluenceChunker):
    """HTML chunker: same as ConfluenceChunker but without Confluence-specific ACL.

    This is the fallback for generic HTML sources (web pages, other scraped content)
    that are not specifically from Confluence or Jira.
    """

    def chunk(
        self,
        doc: CanonicalDocument,
        *,
        tenant_id: str | None = None,
        acl_readers: list[str] | None = None,
        acl_spaces: list[str] | None = None,
        is_public: bool = False,
    ) -> list[ChunkDocument]:
        """Chunk an HTML CanonicalDocument.

        Args:
            doc: CanonicalDocument from HTML source
            tenant_id: Tenant override
            acl_readers: Readers list
            acl_spaces: Spaces list
            is_public: Public flag

        Returns:
            List of ChunkDocuments
        """
        # Use parent ConfluenceChunker logic, but don't inject Confluence space_key
        chunks = []
        chunk_position = 0

        base_chunk = self._base_chunk_doc(
            doc,
            tenant_id=tenant_id,
            acl_readers=acl_readers,
            acl_spaces=acl_spaces or [],
            is_public=is_public,
        )

        # INTRO chunk
        intro_text = self._extract_intro_text(doc)
        if intro_text and self._word_count(intro_text) >= self.MIN_CHUNK_WORDS:
            chunk = ChunkDocument(
                chunk_kind=ChunkKind.INTRO,
                heading="",
                heading_path=[],
                chunk_text=intro_text,
                display_text=intro_text,
                chunk_position=chunk_position,
                total_chunks=0,
                **base_chunk,
            )
            chunks.append(chunk)
            chunk_position += 1

        # SECTION chunks from section_hierarchy
        if doc.section_hierarchy:
            for section_node in doc.section_hierarchy:
                section_chunks = self._chunk_section(
                    section_node,
                    doc,
                    base_chunk,
                    chunk_position,
                )
                chunks.extend(section_chunks)
                chunk_position += len(section_chunks)

        # Update total_chunks
        total = len(chunks)
        for chunk in chunks:
            chunk.total_chunks = total

        return chunks
