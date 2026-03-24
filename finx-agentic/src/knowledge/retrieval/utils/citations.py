from __future__ import annotations

from typing import Any, Dict, List

_ARTIFACT_KINDS = frozenset(
    {"image_caption", "attachment", "chart_summary", "diagram_summary"}
)


# ── MIME classification ──────────────────────────────────────────────────


def classify_mime(mime_type: str) -> str:
    """Map MIME type to a UI-friendly artifact label."""
    if not mime_type:
        return "file"
    if mime_type.startswith(
        ("image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml")
    ):
        return "image"
    if mime_type.startswith("application/pdf"):
        return "pdf"
    if any(
        k in mime_type
        for k in ("spreadsheet", "excel", "csv", "vnd.ms-excel")
    ):
        return "spreadsheet"
    if any(
        k in mime_type
        for k in (
            "wordprocessingml",
            "msword",
            "presentationml",
            "ms-powerpoint",
            "opendocument",
        )
    ):
        return "document"
    return "file"


# ── Source classification ────────────────────────────────────────────────


def extract_parent_title(meta: Dict[str, Any]) -> str:
    """Derive parent page title from *section_path* metadata."""
    for seg in meta.get("section_path", []):
        if seg.startswith("Page:"):
            return seg[5:].strip()
    return ""


def classify_source_type(meta: Dict[str, Any]) -> str:
    """Map source_type + mime_type to a concise LLM-friendly label."""
    source_type = meta.get("source_type", "")
    if source_type == "comment":
        return "comment"
    if source_type == "attachment" or meta.get("artifact_uri"):
        cls = classify_mime(meta.get("mime_type", ""))
        return cls if cls != "document" else "file"
    return "page"


# ── Full citation builder ───────────────────────────────────────────────


def build_full_citation(
    doc: Any,
    index: int,
    existing_count: int,
) -> Dict[str, Any]:
    """Build a full citation dict for the UI (session_state)."""
    meta = doc.meta_data or {}
    chunk_kind = meta.get("chunk_kind", "")
    mime_type = meta.get("mime_type", "")
    artifact_uri = meta.get("artifact_uri", "")
    source_type_raw = meta.get("source_type", "")
    parent_content_id = meta.get("parent_content_id", "")

    citation: dict[str, Any] = {
        "id": meta.get("chunk_id") or meta.get("doc_id") or "",
        "title": doc.name or meta.get("doc_title", ""),
        "source_type": meta.get("source_system") or "knowledge",
        "snippet": (doc.content or "")[:300],
        "content": doc.content or "",
        "chunk_kind": chunk_kind,
        "space_key": meta.get("space_key", ""),
        "external_id": meta.get("external_id", ""),
        "url": meta.get("source_url") or None,
        "score": meta.get("rerank_score"),
        "index": existing_count + index + 1,
        "content_source_type": source_type_raw,
    }

    if parent_content_id:
        citation["parent_content_id"] = parent_content_id
        parent_title = extract_parent_title(meta)
        if parent_title:
            citation["parent_title"] = parent_title

    if artifact_uri:
        citation["artifact_uri"] = artifact_uri
    if mime_type:
        citation["mime_type"] = mime_type

    is_artifact = (
        chunk_kind in _ARTIFACT_KINDS
        or source_type_raw == "attachment"
        or bool(artifact_uri)
    )
    if is_artifact:
        citation["is_artifact"] = True
        citation["artifact_type"] = classify_mime(mime_type)

    return citation


# ── Accumulation ─────────────────────────────────────────────────────────

CITATIONS_STATE_KEY = "_citations"


def accumulate_citations(
    docs: List[Any],
    session_state: Dict[str, Any],
) -> None:
    """Build full UI citations from *docs* and merge into *session_state* (dedup by id)."""
    existing = session_state.get(CITATIONS_STATE_KEY) or []
    existing_count = len(existing)
    seen_ids = {c["id"] for c in existing if c["id"]}
    citations = [
        build_full_citation(doc, i, existing_count)
        for i, doc in enumerate(docs)
    ]
    session_state[CITATIONS_STATE_KEY] = existing + [
        c for c in citations if not c["id"] or c["id"] not in seen_ids
    ]
