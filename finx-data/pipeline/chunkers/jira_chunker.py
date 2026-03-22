"""Jira chunker: type-aware chunking for issues, comments, and attachments.

Produces:
- DOC_HEADER: issue key + summary + status + priority + type (high-signal, short)
- SECTION: description split by headings
- RESOLUTION: resolution chunk for done/resolved issues
- COMMENT: one per comment with author + date
- ATTACHMENT: delegated to DocumentChunker / ExcelChunker / VLM by type

Each chunk carries an embedding prefix:
    [Project: KEY] [Issue: ISSUE-123] [Status] ...
"""

from __future__ import annotations

from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.chunk import ChunkDocument, ChunkKind
from pipeline.chunkers.base import BaseChunker


class JiraChunker(BaseChunker):
    """Chunks Jira content objects by type."""

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
            or doc.metadata.get("content_type", "issue")
        ).lower()

        project_key = doc.metadata.get("project_key", "")
        final_acl_spaces = list(acl_spaces or [])
        if project_key and project_key not in final_acl_spaces:
            final_acl_spaces.append(project_key)

        base_chunk = self._base_chunk_doc(
            doc,
            tenant_id=tenant_id,
            acl_readers=acl_readers,
            acl_spaces=final_acl_spaces,
            is_public=is_public,
        )

        base_chunk["project_key"] = project_key
        base_chunk["source_type"] = content_type
        base_chunk["ticket_status"] = doc.metadata.get("status", "")
        base_chunk["ticket_type"] = doc.metadata.get("issue_type", "")
        base_chunk["parent_content_id"] = doc.metadata.get("parent_content_id", "")

        if content_type == "comment":
            chunks = self._chunk_comment(doc, base_chunk)
        elif content_type == "attachment":
            chunks = self._chunk_attachment(doc, base_chunk)
        else:
            chunks = self._chunk_issue(doc, base_chunk)

        total = len(chunks)
        for c in chunks:
            c.total_chunks = total
        return chunks

    # ── Issue ─────────────────────────────────────────────────────────────

    def _chunk_issue(
        self, doc: CanonicalDocument, base_chunk: dict
    ) -> list[ChunkDocument]:
        chunks: list[ChunkDocument] = []
        pos = 0
        meta = doc.metadata

        issue_key = meta.get("issue_key", doc.source_document_id)
        project_key = meta.get("project_key", "")
        status = meta.get("status", "")
        issue_type = meta.get("issue_type", "")
        priority = meta.get("priority", "")
        assignee = meta.get("assignee", "")
        labels = meta.get("labels", [])

        # Build embedding prefix
        prefix = []
        if project_key:
            prefix.append(f"Project: {project_key}")
        prefix.append(f"Issue: {issue_key}")
        if status:
            prefix.append(f"Status: {status}")

        # DOC_HEADER chunk: compact high-signal metadata
        header_parts = [f"[{issue_key}] {doc.title}"]
        if issue_type:
            header_parts.append(f"Type: {issue_type}")
        if status:
            header_parts.append(f"Status: {status}")
        if priority:
            header_parts.append(f"Priority: {priority}")
        if assignee:
            header_parts.append(f"Assignee: {assignee}")
        if labels:
            header_parts.append(f"Labels: {', '.join(labels)}")

        header_text = " | ".join(header_parts)
        chunks.append(ChunkDocument(
            chunk_kind=ChunkKind.DOC_HEADER,
            heading=doc.title,
            heading_path=[],
            section_path=prefix,
            chunk_text=self._build_prefix(prefix, header_text),
            display_text=header_text,
            chunk_position=pos,
            total_chunks=0,
            **base_chunk,
        ))
        pos += 1

        # SECTION chunks from description (section hierarchy)
        if doc.section_hierarchy:
            for section_node in doc.section_hierarchy:
                section_text = self._extract_section_text(section_node, doc)
                if section_text and self._word_count(section_text) >= self.MIN_CHUNK_WORDS:
                    text_parts = self._split_text_with_overlap(
                        section_text, self.MAX_TOKENS, self.OVERLAP_TOKENS,
                    )
                    section_prefix = prefix + [f"Section: {section_node.title}"]
                    for part in text_parts:
                        chunks.append(ChunkDocument(
                            chunk_kind=ChunkKind.SECTION,
                            heading=section_node.title,
                            heading_path=section_node.path,
                            section_path=section_prefix,
                            chunk_text=self._build_prefix(section_prefix, part),
                            display_text=part,
                            chunk_position=pos,
                            total_chunks=0,
                            **base_chunk,
                        ))
                        pos += 1
        else:
            # No section hierarchy → full description as one SECTION
            full_text = doc.full_text().strip()
            if full_text and self._word_count(full_text) >= self.MIN_CHUNK_WORDS:
                text_parts = self._split_text_with_overlap(
                    full_text, self.MAX_TOKENS, self.OVERLAP_TOKENS,
                )
                for part in text_parts:
                    chunks.append(ChunkDocument(
                        chunk_kind=ChunkKind.SECTION,
                        heading="Description",
                        heading_path=["Description"],
                        section_path=prefix + ["Section: Description"],
                        chunk_text=self._build_prefix(prefix, part),
                        display_text=part,
                        chunk_position=pos,
                        total_chunks=0,
                        **base_chunk,
                    ))
                    pos += 1

        # RESOLUTION chunk for resolved issues
        resolution = meta.get("resolution", "")
        resolved = meta.get("resolved", "")
        if resolution and status and status.lower() in ("done", "closed", "resolved"):
            resolution_text = f"Resolution: {resolution}"
            if resolved:
                resolution_text += f"\nResolved: {resolved}"
            chunks.append(ChunkDocument(
                chunk_kind=ChunkKind.RESOLUTION,
                heading="Resolution",
                heading_path=["Resolution"],
                section_path=prefix + ["Resolution"],
                chunk_text=self._build_prefix(prefix, resolution_text),
                display_text=resolution_text,
                chunk_position=pos,
                total_chunks=0,
                **base_chunk,
            ))
            pos += 1

        return chunks

    # ── Comment ───────────────────────────────────────────────────────────

    def _chunk_comment(
        self, doc: CanonicalDocument, base_chunk: dict
    ) -> list[ChunkDocument]:
        text = doc.full_text().strip()
        if not text or self._word_count(text) < self.MIN_CHUNK_WORDS:
            return []

        author = doc.metadata.get("author", "Unknown")
        parent_key = doc.metadata.get("parent_content_id", "")
        comment_meta = f"Comment by {author}"
        if parent_key:
            comment_meta += f" on {parent_key}"

        return [ChunkDocument(
            chunk_kind=ChunkKind.COMMENT,
            heading=comment_meta,
            heading_path=[],
            section_path=[],
            comment_id=doc.source_document_id or doc.metadata.get("content_id", ""),
            chunk_text=f"[{comment_meta}]\n\n{text}",
            display_text=text,
            chunk_position=0,
            total_chunks=0,
            **base_chunk,
        )]

    # ── Attachment ────────────────────────────────────────────────────────

    def _chunk_attachment(
        self, doc: CanonicalDocument, base_chunk: dict
    ) -> list[ChunkDocument]:
        """Chunk an already-extracted attachment document."""
        text = doc.full_text().strip()
        if not text or self._word_count(text) < self.MIN_CHUNK_WORDS:
            return []

        att_id = doc.metadata.get("content_id", doc.source_document_id)
        mime = doc.metadata.get("media_type", "")
        base_chunk["attachment_id"] = att_id
        base_chunk["mime_type"] = mime

        chunks: list[ChunkDocument] = []
        pos = 0

        # Image → IMAGE_CAPTION
        if mime.startswith("image/"):
            chunks.append(ChunkDocument(
                chunk_kind=ChunkKind.IMAGE_CAPTION,
                heading=f"Image: {doc.title}",
                heading_path=[],
                section_path=[],
                chunk_text=text,
                display_text=text,
                chunk_position=0,
                total_chunks=0,
                **base_chunk,
            ))
            return chunks

        # Other → ATTACHMENT chunks
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

    # ── helpers ───────────────────────────────────────────────────────────

    def _extract_section_text(self, section_node, doc: CanonicalDocument) -> str:
        parts = []
        for idx in section_node.block_indices:
            if idx < len(doc.content_blocks):
                block = doc.content_blocks[idx]
                if hasattr(block, "content") and hasattr(block, "block_type"):
                    if block.block_type.value != "heading":
                        parts.append(block.content)
                elif hasattr(block, "items"):
                    parts.append("\n".join(f"- {i}" for i in block.items))
                elif hasattr(block, "markdown"):
                    parts.append(block.markdown)
        return "\n\n".join(parts).strip()

    @staticmethod
    def _build_prefix(prefix: list[str], content: str) -> str:
        if not prefix:
            return content
        header = "\n".join(f"[{p}]" for p in prefix)
        return f"{header}\n\n{content}"
