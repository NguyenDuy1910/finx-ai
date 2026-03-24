from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.knowledge.retrieval.confluence_knowledge import RetrievalStore


class ContextExpander:
    """Expand retrieved points with sibling section and neighbor chunks."""

    def __init__(self, store: RetrievalStore) -> None:
        self.store = store

    def expand(self, points: list[Any], target_count: int) -> list[Any]:
        if not points:
            return []

        seen_ids: set[str] = set()
        merged: list[Any] = []

        def _add(point: Any) -> None:
            pid = str(getattr(point, "id", ""))
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                merged.append(point)

        for point in points:
            _add(point)

        cfg = self.store.config
        for point in points:
            if len(merged) >= target_count:
                break

            payload: dict[str, Any] = getattr(point, "payload", {}) or {}

            if cfg.expand_section_context:
                section_id = payload.get("section_id")
                if section_id:
                    for p in self.store.get_section_points(
                        section_id=str(section_id),
                        limit=cfg.max_section_expansion,
                    ):
                        _add(p)

            if cfg.expand_neighbor_window > 0:
                doc_id = payload.get("doc_id")
                chunk_position = payload.get("chunk_position")
                if doc_id is not None and chunk_position is not None:
                    for p in self.store.get_neighbor_points(
                        doc_id=str(doc_id),
                        chunk_position=int(chunk_position),
                        window=cfg.expand_neighbor_window,
                        limit=cfg.max_neighbor_expansion,
                    ):
                        _add(p)

        return merged