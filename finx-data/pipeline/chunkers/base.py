"""BaseChunker ABC and shared text-splitting utilities."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.chunk import ChunkDocument, ChunkKind


class BaseChunker(ABC):
    """Base class for all chunkers. Converts CanonicalDocument → list[ChunkDocument]."""

    MAX_TOKENS: int = 400  # Default max tokens per text chunk
    OVERLAP_TOKENS: int = 50  # Overlap between consecutive text chunks
    MIN_CHUNK_WORDS: int = 10  # Skip trivially short chunks

    def __init__(
        self,
        *,
        max_tokens: int = 400,
        overlap_tokens: int = 50,
        min_chunk_words: int = 10,
        default_tenant_id: str = "default",
    ) -> None:
        """Initialize chunker.

        Args:
            max_tokens: Maximum tokens per chunk.
            overlap_tokens: Overlap between chunks.
            min_chunk_words: Minimum words to produce a chunk (avoid trivial chunks).
            default_tenant_id: Default tenant for all chunks.
        """
        self.MAX_TOKENS = max_tokens
        self.OVERLAP_TOKENS = overlap_tokens
        self.MIN_CHUNK_WORDS = min_chunk_words
        self.default_tenant_id = default_tenant_id

        # Initialize tiktoken if available
        if TIKTOKEN_AVAILABLE:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        else:
            self.encoding = None

    @abstractmethod
    def chunk(
        self,
        doc: CanonicalDocument,
        *,
        tenant_id: str | None = None,
        acl_readers: list[str] | None = None,
        acl_spaces: list[str] | None = None,
        is_public: bool = False,
    ) -> list[ChunkDocument]:
        """Produce ordered list of ChunkDocuments from a CanonicalDocument.

        Args:
            doc: Source CanonicalDocument.
            tenant_id: Tenant override. Defaults to self.default_tenant_id.
            acl_readers: User/group IDs with read access.
            acl_spaces: Space/project keys granting access.
            is_public: If True, any authenticated user in tenant can read.

        Returns:
            List of ChunkDocument objects, in order.
        """
        ...

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses tiktoken if available, otherwise conservative char-based estimate.
        For Vietnamese content without tiktoken: ~2 chars per token.
        """
        if self.encoding:
            try:
                return len(self.encoding.encode(text))
            except Exception:
                pass

        # Fallback: 2 chars per token (conservative for Vietnamese)
        return max(1, len(text) // 2)

    def _split_text_with_overlap(
        self,
        text: str,
        max_tokens: int,
        overlap_tokens: int,
    ) -> list[str]:
        """Split text into overlapping chunks at sentence boundaries.

        Strategy: Split on paragraph breaks (\n\n), then on sentence ends (. ),
        never mid-word. Each chunk = ~max_tokens, with overlap_tokens overlap.

        Args:
            text: Text to split.
            max_tokens: Target max tokens per chunk.
            overlap_tokens: Tokens to overlap between chunks.

        Returns:
            List of text chunks.
        """
        if self._estimate_tokens(text) <= max_tokens:
            return [text]  # No split needed

        chunks = []
        step_tokens = max(1, max_tokens - overlap_tokens)

        # First try paragraph boundaries
        paragraphs = text.split("\n\n")
        if len(paragraphs) > 1:
            return self._chunk_paragraphs(paragraphs, max_tokens, overlap_tokens)

        # Fall back to sentence splitting
        sentences = self._split_sentences(text)
        if len(sentences) > 1:
            return self._chunk_sentences(sentences, max_tokens, overlap_tokens)

        # Fallback: character-based split (for text with no sentence markers)
        return self._chunk_by_words(text.split(), max_tokens, overlap_tokens)

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences. Handles . ! ? as sentence ends."""
        # Match sentence boundaries: . ! ? followed by space or EOL
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [p.strip() for p in parts if p.strip()]

    def _chunk_paragraphs(
        self,
        paragraphs: list[str],
        max_tokens: int,
        overlap_tokens: int,
    ) -> list[str]:
        """Build chunks from paragraph-split text."""
        chunks = []
        current_chunk = ""
        current_tokens = 0
        step_tokens = max(1, max_tokens - overlap_tokens)

        for para in paragraphs:
            para_tokens = self._estimate_tokens(para)

            if not current_chunk:
                # Start new chunk
                current_chunk = para
                current_tokens = para_tokens
            elif current_tokens + para_tokens <= max_tokens:
                # Append to current chunk
                current_chunk += "\n\n" + para
                current_tokens += 2 + para_tokens  # +2 for \n\n
            else:
                # Chunk full, save and start new
                if current_chunk.strip():
                    chunks.append(current_chunk)

                # Start overlap: use last part of current chunk
                overlap_para = ""
                for sent in self._split_sentences(current_chunk):
                    if (
                        self._estimate_tokens(overlap_para + " " + sent)
                        <= overlap_tokens
                    ):
                        overlap_para += " " + sent if overlap_para else sent
                    else:
                        break

                current_chunk = (overlap_para + "\n\n" + para).strip()
                current_tokens = (
                    self._estimate_tokens(overlap_para)
                    + 2
                    + self._estimate_tokens(para)
                )

        # Don't forget final chunk
        if current_chunk.strip():
            chunks.append(current_chunk)

        return chunks

    def _chunk_sentences(
        self,
        sentences: list[str],
        max_tokens: int,
        overlap_tokens: int,
    ) -> list[str]:
        """Build chunks from sentence-split text."""
        chunks = []
        current_chunk = ""
        current_tokens = 0

        for sent in sentences:
            sent_tokens = self._estimate_tokens(sent)

            if not current_chunk:
                current_chunk = sent
                current_tokens = sent_tokens
            elif current_tokens + 1 + sent_tokens <= max_tokens:  # +1 for space
                current_chunk += " " + sent
                current_tokens += 1 + sent_tokens
            else:
                # Chunk full
                if current_chunk.strip():
                    chunks.append(current_chunk)

                # Start overlap: last ~overlap_tokens of current chunk
                words = current_chunk.split()
                overlap_words = []
                for word in reversed(words):
                    if (
                        self._estimate_tokens(" ".join(reversed(overlap_words + [word])))
                        <= overlap_tokens
                    ):
                        overlap_words.insert(0, word)
                    else:
                        break

                overlap_text = " ".join(overlap_words)
                current_chunk = (overlap_text + " " + sent).strip()
                current_tokens = (
                    self._estimate_tokens(overlap_text)
                    + 1
                    + self._estimate_tokens(sent)
                )

        if current_chunk.strip():
            chunks.append(current_chunk)

        return chunks

    def _chunk_by_words(
        self,
        words: list[str],
        max_tokens: int,
        overlap_tokens: int,
    ) -> list[str]:
        """Build chunks from word list (fallback)."""
        chunks = []
        current_chunk: list[str] = []
        current_tokens = 0
        step_tokens = max(1, max_tokens - overlap_tokens)

        for word in words:
            word_tokens = self._estimate_tokens(word)

            if not current_chunk:
                current_chunk = [word]
                current_tokens = word_tokens
            elif current_tokens + 1 + word_tokens <= max_tokens:
                current_chunk.append(word)
                current_tokens += 1 + word_tokens
            else:
                # Chunk full
                if current_chunk:
                    chunks.append(" ".join(current_chunk))

                # Start overlap
                overlap_words = []
                for w in reversed(current_chunk):
                    if (
                        self._estimate_tokens(" ".join(reversed(overlap_words + [w])))
                        <= overlap_tokens
                    ):
                        overlap_words.insert(0, w)
                    else:
                        break

                current_chunk = overlap_words + [word]
                current_tokens = (
                    self._estimate_tokens(" ".join(overlap_words))
                    + 1
                    + self._estimate_tokens(word)
                )

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def _make_chunk_text(self, heading: str, body: str) -> str:
        """Construct plain text for embedding from heading + body."""
        if heading:
            return f"{heading}\n\n{body}".strip()
        return body.strip()

    def _base_chunk_doc(
        self,
        doc: CanonicalDocument,
        tenant_id: str | None = None,
        acl_readers: list[str] | None = None,
        acl_spaces: list[str] | None = None,
        is_public: bool = False,
    ) -> dict:
        """Return base ChunkDocument fields common across all chunkers."""
        return {
            "tenant_id": tenant_id or self.default_tenant_id,
            "doc_id": doc.document_id,
            "external_id": doc.source_document_id,
            "source_url": doc.metadata.get("confluence_url", "") or doc.metadata.get("source_url", "") or doc.source_uri,
            "doc_title": doc.title,
            "language": doc.metadata.get("language", "en"),
            "doc_type": doc.metadata.get("document_type", ""),
            "domains": doc.metadata.get("domains", []) or doc.tags,
            "source_system": doc.source_system,
            "artifact_uri": doc.metadata.get("artifact_uri", ""),
            "source_created_at": doc.source_created_at,
            "source_updated_at": doc.source_modified_at,
            "ingested_at": datetime.now(timezone.utc),
            "doc_hash": doc.metadata.get("content_hash", ""),
            "quality_score": doc.metadata.get("quality_score", 0.0),
            "acl_readers": acl_readers or [],
            "acl_spaces": acl_spaces or [],
            "is_public": is_public,
            "summary": doc.metadata.get("summary", ""),
            "keywords": doc.metadata.get("key_entities", []),
            "acronym_expansions": doc.metadata.get("abbreviations", {}),
            "embedding_model": "text-embedding-3-small",
            "embedding_version": "v2",
            "pipeline_version": doc.provenance.pipeline_version or "",
        }

    def _word_count(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())
