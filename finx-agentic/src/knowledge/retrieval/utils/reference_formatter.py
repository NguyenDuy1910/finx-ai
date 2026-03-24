from __future__ import annotations

import re
from typing import Any


# ── standalone helpers (imported by utils/__init__ and context_packer) ────


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace into single spaces and strip."""
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, max_chars: int, *, suffix: str = "...") -> str:
    """Shorten *text* to at most *max_chars*, appending *suffix* when cut."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(suffix)].rstrip() + suffix


# ── main formatter ───────────────────────────────────────────────────────


class ReferenceFormatter:
    """Convert Qdrant scored points into Agno retriever output: list[dict]."""

    def __init__(self, *, max_content_chars: int = 2200) -> None:
        self.max_content_chars = max_content_chars

    def format_many(self, points: list[Any], limit: int) -> list[dict[str, Any]]:
        return [self.format_one(point) for point in points[:limit]]

    def format_one(self, point: Any) -> dict[str, Any]:
        payload: dict[str, Any] = getattr(point, "payload", {}) or {}

        doc_title = _clean(payload.get("doc_title"))
        heading = _clean(payload.get("heading"))
        section_path: list[str] = payload.get("section_path") or []
        chunk_kind = _clean(payload.get("chunk_kind"))
        source_system = _clean(payload.get("source_system"))
        source_url = _clean(payload.get("source_url"))

        content = (
            _clean(payload.get("display_text"))
            or _clean(payload.get("chunk_text"))
            or _clean(payload.get("summary"))
        )
        content = truncate(content, self.max_content_chars)

        title_parts = [p for p in (doc_title, heading) if p]
        title = " > ".join(title_parts) if title_parts else "Retrieved knowledge"

        metadata: dict[str, Any] = {
            "doc_id": payload.get("doc_id"),
            "chunk_id": payload.get("chunk_id"),
            "section_id": payload.get("section_id"),
            "chunk_kind": chunk_kind or None,
            "source_system": source_system or None,
            "source_url": source_url or None,
            "section_path": section_path or None,
            "chunk_position": payload.get("chunk_position"),
            "total_chunks": payload.get("total_chunks"),
            "quality_score": payload.get("quality_score"),
            "score": getattr(point, "score", None),
        }

        return {
            "name": title,
            "content": self._build_content_block(
                title=title,
                section_path=section_path,
                chunk_kind=chunk_kind,
                source_system=source_system,
                content=content,
                source_url=source_url,
            ),
            "metadata": {k: v for k, v in metadata.items() if v is not None},
        }

    # ── private ──────────────────────────────────────────────────────

    @staticmethod
    def _build_content_block(
        *,
        title: str,
        section_path: list[str],
        chunk_kind: str,
        source_system: str,
        content: str,
        source_url: str,
    ) -> str:
        lines: list[str] = [f"Title: {title}"]

        if section_path:
            lines.append(
                f"Section path: {' > '.join(str(p) for p in section_path if str(p).strip())}"
            )
        if chunk_kind:
            lines.append(f"Chunk kind: {chunk_kind}")
        if source_system:
            lines.append(f"Source: {source_system}")
        if source_url:
            lines.append(f"Source URL: {source_url}")

        lines.append("Content:")
        lines.append(content or "")

        return "\n".join(lines)


def _clean(value: Any) -> str:
    """Return stripped string or empty string for None."""
    return str(value).strip() if value is not None else ""
