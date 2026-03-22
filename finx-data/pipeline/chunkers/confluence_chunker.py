"""Confluence chunker: type-aware chunking for pages, blog posts, comments, and attachments.

Dispatches by ``source_content_type`` to produce the correct chunk kinds:
- page / blogpost → INTRO + SECTION chunks (section-aware)
- comment        → standalone COMMENT chunks (never merged into parent)
- attachment     → delegates to DocumentChunker / ExcelChunker / creates IMAGE_CAPTION

Each chunk carries a structured ``section_path`` for embedding prefix and
``parent_content_id`` for content-graph linking.
"""

from __future__ import annotations

from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.chunk import ChunkDocument, ChunkKind
from pipeline.chunkers.base import BaseChunker


class ConfluenceChunker(BaseChunker):
    """Chunks Confluence content objects by type.

    Routing:
    - page / blogpost → ``_chunk_page()``
    - comment         → ``_chunk_comment()``
    - attachment      → ``_chunk_attachment()``

    ACL: All chunks inherit ``acl_spaces`` from Confluence ``space_key``.
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
        content_type = (
            doc.source_content_type
            or doc.metadata.get("content_type", "page")
        ).lower()

        # Ensure acl_spaces includes the Confluence space
        confluence_space = doc.metadata.get("space_key", "")
        final_acl_spaces = list(acl_spaces or [])
        if confluence_space and confluence_space not in final_acl_spaces:
            final_acl_spaces.append(confluence_space)

        base_chunk = self._base_chunk_doc(
            doc,
            tenant_id=tenant_id,
            acl_readers=acl_readers,
            acl_spaces=final_acl_spaces,
            is_public=is_public,
        )

        # Inject content-graph linking fields into base
        base_chunk["space_key"] = confluence_space
        base_chunk["source_type"] = content_type
        base_chunk["body_representation"] = doc.metadata.get("body_representation", "")
        base_chunk["parent_content_id"] = doc.metadata.get("parent_content_id", "")

        if content_type == "comment":
            chunks = self._chunk_comment(doc, base_chunk)
        elif content_type == "attachment":
            chunks = self._chunk_attachment(doc, base_chunk)
        else:
            # page, blogpost, or unspecified
            chunks = self._chunk_page(doc, base_chunk, content_type)

        # Update total and return
        total = len(chunks)
        for c in chunks:
            c.total_chunks = total
        return chunks

    # ── Page / Blog Post ──────────────────────────────────────────────────

    def _chunk_page(
        self,
        doc: CanonicalDocument,
        base_chunk: dict,
        content_type: str,
    ) -> list[ChunkDocument]:
        """Chunk a page or blog post into INTRO + SECTION chunks."""
        chunks: list[ChunkDocument] = []
        pos = 0
        is_blog = content_type == "blogpost"
        space_key = doc.metadata.get("space_key", "")

        # Build section_path prefix for embedding
        path_prefix = []
        if space_key:
            path_prefix.append(f"Space: {space_key}")
        path_prefix.append(f"{'Blog' if is_blog else 'Page'}: {doc.title}")

        # INTRO chunk: text before first heading
        intro_text = self._extract_intro_text(doc)
        if intro_text and self._word_count(intro_text) >= self.MIN_CHUNK_WORDS:
            chunks.append(ChunkDocument(
                chunk_kind=ChunkKind.BLOG_INTRO if is_blog else ChunkKind.INTRO,
                heading="",
                heading_path=[],
                section_path=path_prefix,
                chunk_text=self._build_embedding_text(path_prefix, intro_text),
                display_text=intro_text,
                chunk_position=pos,
                total_chunks=0,
                **base_chunk,
            ))
            pos += 1

        # SECTION chunks from section hierarchy
        if doc.section_hierarchy:
            for section_node in doc.section_hierarchy:
                section_chunks = self._chunk_section(
                    section_node, doc, base_chunk, pos,
                    path_prefix=path_prefix,
                    is_blog=is_blog,
                )
                chunks.extend(section_chunks)
                pos += len(section_chunks)

        return chunks

    # ── Comment ───────────────────────────────────────────────────────────

    def _chunk_comment(
        self,
        doc: CanonicalDocument,
        base_chunk: dict,
    ) -> list[ChunkDocument]:
        """Chunk a standalone comment document.

        Comments are NEVER merged into the parent page body. They are
        indexed as separate objects linked via ``parent_content_id``.
        """
        text = doc.full_text().strip()
        if not text or self._word_count(text) < self.MIN_CHUNK_WORDS:
            return []

        author = doc.metadata.get("author", "Unknown")
        comment_location = doc.metadata.get("comment_location", "")
        parent_title = doc.metadata.get("parent_title", "")

        comment_meta = f"Comment by {author}"
        if comment_location:
            comment_meta += f" ({comment_location})"
        if parent_title:
            comment_meta += f" on: {parent_title}"

        chunk_text = f"[{comment_meta}]\n\n{text}"

        return [ChunkDocument(
            chunk_kind=ChunkKind.COMMENT,
            heading=comment_meta,
            heading_path=[],
            section_path=[],
            comment_id=doc.source_document_id or doc.metadata.get("content_id", ""),
            chunk_text=chunk_text,
            display_text=text,
            chunk_position=0,
            total_chunks=0,
            **base_chunk,
        )]

    # ── Attachment ────────────────────────────────────────────────────────

    def _chunk_attachment(
        self,
        doc: CanonicalDocument,
        base_chunk: dict,
    ) -> list[ChunkDocument]:
        """Chunk an attachment that has already been extracted.

        For images: creates a single IMAGE_CAPTION chunk from VLM output.
        For documents: uses the section hierarchy if present, else plain text.
        """
        chunks: list[ChunkDocument] = []
        pos = 0
        att_id = doc.metadata.get("content_id", doc.source_document_id)
        mime = doc.metadata.get("media_type", "")
        parent_title = doc.metadata.get("parent_title", "")
        space_key = doc.metadata.get("space_key", "")

        base_chunk["attachment_id"] = att_id
        base_chunk["mime_type"] = mime

        # Image attachment → specialized chunks by block type
        if mime.startswith("image/"):
            for block in doc.content_blocks:
                bt = getattr(block, "block_type", None)
                if bt is None:
                    continue
                bt_val = bt.value

                if bt_val == "image":
                    description = getattr(block, "description", "") or ""
                    if description and self._word_count(description) >= self.MIN_CHUNK_WORDS:
                        prefix = []
                        if space_key:
                            prefix.append(f"Space: {space_key}")
                        if parent_title:
                            prefix.append(f"Page: {parent_title}")
                        prefix.append(f"Attachment: {doc.title}")
                        chunks.append(ChunkDocument(
                            chunk_kind=ChunkKind.IMAGE_CAPTION,
                            heading=f"Image: {doc.title}",
                            heading_path=[],
                            section_path=prefix,
                            chunk_text=self._build_embedding_text(prefix, description),
                            display_text=description,
                            chunk_position=pos,
                            total_chunks=0,
                            **base_chunk,
                        ))
                        pos += 1

                elif bt_val == "text":
                    text = getattr(block, "content", "")
                    if text and self._word_count(text) >= self.MIN_CHUNK_WORDS:
                        chunks.append(ChunkDocument(
                            chunk_kind=ChunkKind.ATTACHMENT,
                            heading=doc.title,
                            heading_path=[],
                            chunk_text=text,
                            display_text=text,
                            chunk_position=pos,
                            total_chunks=0,
                            **base_chunk,
                        ))
                        pos += 1

                elif bt_val == "key_value":
                    kv_text = "\n".join(
                        f"{p.get('key', '')}: {p.get('value', '')}"
                        for p in block.pairs if p.get("key")
                    )
                    if kv_text and self._word_count(kv_text) >= self.MIN_CHUNK_WORDS:
                        chunks.append(ChunkDocument(
                            chunk_kind=ChunkKind.KEY_VALUE,
                            heading=f"Extracted fields: {doc.title}",
                            heading_path=[],
                            chunk_text=kv_text,
                            display_text=kv_text,
                            content_type="key_value",
                            chunk_position=pos,
                            total_chunks=0,
                            **base_chunk,
                        ))
                        pos += 1

                elif bt_val == "chart":
                    parts = []
                    if block.title:
                        parts.append(f"Chart: {block.title}")
                    if getattr(block, "trend_summary", ""):
                        parts.append(block.trend_summary)
                    if getattr(block, "description", ""):
                        parts.append(block.description)
                    chart_text = "\n".join(parts)
                    if chart_text and self._word_count(chart_text) >= self.MIN_CHUNK_WORDS:
                        chunks.append(ChunkDocument(
                            chunk_kind=ChunkKind.CHART_SUMMARY,
                            heading=block.title or doc.title,
                            heading_path=[],
                            chunk_text=chart_text,
                            display_text=chart_text,
                            content_type="chart",
                            chunk_position=pos,
                            total_chunks=0,
                            **base_chunk,
                        ))
                        pos += 1

                elif bt_val == "diagram":
                    parts = []
                    if block.title:
                        parts.append(f"Diagram: {block.title}")
                    if getattr(block, "description", ""):
                        parts.append(block.description)
                    diagram_text = "\n".join(parts)
                    if diagram_text and self._word_count(diagram_text) >= self.MIN_CHUNK_WORDS:
                        chunks.append(ChunkDocument(
                            chunk_kind=ChunkKind.DIAGRAM_SUMMARY,
                            heading=block.title or doc.title,
                            heading_path=[],
                            chunk_text=diagram_text,
                            display_text=diagram_text,
                            content_type="diagram",
                            chunk_position=pos,
                            total_chunks=0,
                            **base_chunk,
                        ))
                        pos += 1

            return chunks

        # Document attachment (PDF, DOCX, etc.) → use section-based chunking
        if doc.section_hierarchy:
            prefix = []
            if space_key:
                prefix.append(f"Space: {space_key}")
            if parent_title:
                prefix.append(f"Page: {parent_title}")
            prefix.append(f"Attachment: {doc.title}")

            for section_node in doc.section_hierarchy:
                section_chunks = self._chunk_section(
                    section_node, doc, base_chunk, pos,
                    path_prefix=prefix,
                    is_blog=False,
                )
                chunks.extend(section_chunks)
                pos += len(section_chunks)
        else:
            # Fallback: full text as single ATTACHMENT chunk
            text = doc.full_text().strip()
            if text and self._word_count(text) >= self.MIN_CHUNK_WORDS:
                text_parts = self._split_text_with_overlap(
                    text, self.MAX_TOKENS, self.OVERLAP_TOKENS,
                )
                for part in text_parts:
                    chunks.append(ChunkDocument(
                        chunk_kind=ChunkKind.ATTACHMENT,
                        heading=doc.title,
                        heading_path=[],
                        section_path=[],
                        chunk_text=part,
                        display_text=part,
                        chunk_position=pos,
                        total_chunks=0,
                        **base_chunk,
                    ))
                    pos += 1

        return chunks

    # ── shared helpers ────────────────────────────────────────────────────

    def _extract_intro_text(self, doc: CanonicalDocument) -> str:
        """Extract text blocks that appear before the first heading."""
        intro_blocks = []

        for block in doc.content_blocks:
            if hasattr(block, "block_type") and block.block_type.value == "heading":
                break

            if hasattr(block, "block_type"):
                if block.block_type.value == "text":
                    intro_blocks.append(block.content)
                elif block.block_type.value == "code":
                    intro_blocks.append(f"```\n{block.content}\n```")
                elif block.block_type.value == "list":
                    intro_blocks.append("\n".join(f"- {item}" for item in block.items))

        return "\n\n".join(intro_blocks).strip()

    def _chunk_section(
        self,
        section_node,
        doc: CanonicalDocument,
        base_chunk: dict,
        position_offset: int,
        *,
        path_prefix: list[str] | None = None,
        is_blog: bool = False,
    ) -> list[ChunkDocument]:
        """Chunk one section and its subsections recursively."""
        chunks = []
        position = position_offset

        section_text = self._extract_section_text(section_node, doc)

        if section_text and self._word_count(section_text) >= self.MIN_CHUNK_WORDS:
            text_chunks = self._split_text_with_overlap(
                section_text, self.MAX_TOKENS, self.OVERLAP_TOKENS,
            )

            section_path = list(path_prefix or [])
            section_path.append(f"Section: {' > '.join(section_node.path)}")

            kind = ChunkKind.BLOG_SECTION if is_blog else ChunkKind.SECTION

            for text_chunk in text_chunks:
                chunks.append(ChunkDocument(
                    chunk_kind=kind,
                    heading=section_node.title,
                    heading_path=section_node.path,
                    section_path=section_path,
                    chunk_text=self._build_embedding_text(section_path, text_chunk),
                    display_text=text_chunk,
                    chunk_position=position,
                    total_chunks=0,
                    **base_chunk,
                ))
                position += 1

        for child in section_node.children:
            child_chunks = self._chunk_section(
                child, doc, base_chunk, position,
                path_prefix=path_prefix, is_blog=is_blog,
            )
            chunks.extend(child_chunks)
            position += len(child_chunks)

        return chunks

    def _extract_section_text(self, section_node, doc: CanonicalDocument) -> str:
        """Extract text content for a section from its block_indices."""
        section_blocks = []

        for block_idx in section_node.block_indices:
            if block_idx < len(doc.content_blocks):
                block = doc.content_blocks[block_idx]

                if hasattr(block, "block_type"):
                    block_type = block.block_type.value

                    if block_type == "text":
                        section_blocks.append(block.content)
                    elif block_type == "code":
                        lang = getattr(block, "language", "") or ""
                        section_blocks.append(f"```{lang}\n{block.content}\n```")
                    elif block_type == "list":
                        marker = "✓" if getattr(block, "ordered", False) else "•"
                        items = "\n".join(f"{marker} {item}" for item in block.items)
                        section_blocks.append(items)
                    elif block_type == "table":
                        section_blocks.append(block.markdown)
                    elif block_type == "image":
                        caption = getattr(block, "description", "") or getattr(block, "alt_text", "")
                        if caption:
                            section_blocks.append(f"[Image: {caption}]")
                    elif block_type == "key_value":
                        lines = [f"{p.get('key', '')}: {p.get('value', '')}" for p in block.pairs if p.get("key")]
                        if lines:
                            section_blocks.append("\n".join(lines))
                    elif block_type == "chart":
                        parts = []
                        if block.title:
                            parts.append(f"Chart: {block.title}")
                        if block.trend_summary:
                            parts.append(block.trend_summary)
                        elif block.description:
                            parts.append(block.description)
                        if parts:
                            section_blocks.append("\n".join(parts))
                    elif block_type == "diagram":
                        parts = []
                        if block.title:
                            parts.append(f"Diagram: {block.title}")
                        if block.description:
                            parts.append(block.description)
                        if parts:
                            section_blocks.append("\n".join(parts))

        return "\n\n".join(section_blocks).strip()

    @staticmethod
    def _build_embedding_text(prefix: list[str], content: str) -> str:
        """Build embedding text with structural prefix."""
        if not prefix:
            return content
        header = "\n".join(f"[{p}]" for p in prefix)
        return f"{header}\n\n{content}"
