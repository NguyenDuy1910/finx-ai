from __future__ import annotations

import logging

from src.core.llm.protocol import LLMAdapter
from .models import (
    GRAPH_FIELD_SEP,
    EdgeData,
    NodeData,
    RawEdge,
    RawNode,
)
from .store import GraphStore
from .prompts import DESCRIPTION_SUMMARY

logger = logging.getLogger(__name__)


class Merger:
    def __init__(
        self,
        store: GraphStore,
        *,
        llm: LLMAdapter | None = None,
        max_source_ids: int = 300,
        summary_token_threshold: int = 4000,
    ) -> None:
        self._store = store
        self._max_source_ids = max_source_ids
        self._llm = llm
        self._summary_token_threshold = summary_token_threshold

    def merge_and_upsert_node(self, raw: RawNode) -> NodeData:
        existing = self._store.get_node(raw.name)
        node = self._merge_node(existing, raw) if existing else self._new_node(raw)
        self._store.upsert_node(node)
        return node

    def merge_and_upsert_edge(self, raw: RawEdge) -> EdgeData:
        src_id = raw.src.upper().strip()
        tgt_id = raw.tgt.upper().strip()
        if src_id == tgt_id:
            logger.debug("Skipping self-loop: %s", src_id)
            return EdgeData(src=src_id, tgt=tgt_id, edge_type=raw.edge_type)
        existing = self._store.get_edge(src_id, tgt_id, raw.edge_type)
        edge = self._merge_edge(existing, raw) if existing else self._new_edge(raw)
        self._store.upsert_edge(edge)
        return edge

    async def amerge_batch(
        self,
        raw_nodes: list[RawNode],
        raw_edges: list[RawEdge],
    ) -> tuple[list[NodeData], list[EdgeData]]:
        existing_map = self._store.get_nodes_batch([r.name for r in raw_nodes])

        merged_nodes: list[NodeData] = []
        seen_node_ids: set[str] = set()
        for raw in raw_nodes:
            node_id = raw.node_id
            if node_id in seen_node_ids:
                continue
            seen_node_ids.add(node_id)
            existing = existing_map.get(node_id)
            node = self._merge_node(existing, raw) if existing else self._new_node(raw)
            merged_nodes.append(node)

        merged_edges: list[EdgeData] = []
        seen_edge_ids: set[str] = set()
        for raw in raw_edges:
            src_id = raw.src.upper().strip()
            tgt_id = raw.tgt.upper().strip()
            if src_id == tgt_id:
                continue
            edge_id = f"{src_id}|{raw.edge_type}|{tgt_id}"
            if edge_id in seen_edge_ids:
                continue
            seen_edge_ids.add(edge_id)
            merged_edges.append(self._new_edge(raw))

        return merged_nodes, merged_edges

    def _new_node(self, raw: RawNode) -> NodeData:
        return NodeData(
            name=raw.name.upper().strip(),
            label=self._normalise_label(raw.entity_type),
            description=raw.description,
            synonyms=list(raw.synonyms),
            tags=list(raw.tags),
            source_ids=[raw.source_id] if raw.source_id else [],
            file_path=raw.file_path,
        )

    def _new_edge(self, raw: RawEdge) -> EdgeData:
        return EdgeData(
            src=raw.src.upper().strip(),
            tgt=raw.tgt.upper().strip(),
            edge_type=raw.edge_type,
            description=raw.description,
            keywords=raw.keywords,
            weight=raw.weight,
            source_ids=[raw.source_id] if raw.source_id else [],
        )

    def _merge_node(self, existing: NodeData, raw: RawNode) -> NodeData:
        descriptions = []
        if existing.description:
            descriptions.append(existing.description)
        if raw.description and raw.description not in descriptions:
            descriptions.append(raw.description)

        if len(descriptions) <= 1:
            merged_desc = descriptions[0] if descriptions else ""
        elif self._estimate_tokens(descriptions) > self._summary_token_threshold:
            merged_desc = self._summarise_descriptions(raw.name, descriptions)
        else:
            merged_desc = GRAPH_FIELD_SEP.join(descriptions)

        merged_synonyms = list(dict.fromkeys(existing.synonyms + raw.synonyms))
        merged_tags = list(dict.fromkeys(existing.tags + raw.tags))

        merged_sources = list(dict.fromkeys(
            existing.source_ids + ([raw.source_id] if raw.source_id else [])
        ))
        if len(merged_sources) > self._max_source_ids:
            merged_sources = merged_sources[-self._max_source_ids:]

        label = existing.label or self._normalise_label(raw.entity_type)

        return NodeData(
            name=existing.name,
            label=label,
            description=merged_desc,
            domain=existing.domain or "",
            synonyms=merged_synonyms,
            tags=merged_tags,
            source_ids=merged_sources,
            file_path=existing.file_path or raw.file_path,
            extra=existing.extra,
        )

    def _merge_edge(self, existing: EdgeData, raw: RawEdge) -> EdgeData:
        descriptions = []
        if existing.description:
            descriptions.append(existing.description)
        if raw.description and raw.description not in descriptions:
            descriptions.append(raw.description)
        merged_desc = GRAPH_FIELD_SEP.join(descriptions) if descriptions else ""

        kw_set: set[str] = set()
        for kw_str in [existing.keywords, raw.keywords]:
            for kw in kw_str.split(","):
                kw = kw.strip()
                if kw:
                    kw_set.add(kw)
        merged_kw = ", ".join(sorted(kw_set))

        merged_weight = max(existing.weight, raw.weight)

        merged_sources = list(dict.fromkeys(
            existing.source_ids + ([raw.source_id] if raw.source_id else [])
        ))

        return EdgeData(
            src=existing.src,
            tgt=existing.tgt,
            edge_type=existing.edge_type,
            description=merged_desc,
            keywords=merged_kw,
            weight=merged_weight,
            source_ids=merged_sources,
        )

    def _summarise_descriptions(self, entity_name: str, descriptions: list[str]) -> str:
        if self._llm is None:
            return GRAPH_FIELD_SEP.join(descriptions)

        prompt = DESCRIPTION_SUMMARY.replace(
            "{entity_name}", entity_name
        ).replace(
            "{descriptions}", "\n---\n".join(descriptions)
        )
        system = (
            "You are a Knowledge Graph description summarizer for a Vietnamese banking platform. "
            "Synthesize multiple descriptions into ONE concise, comprehensive summary. "
            "Preserve Vietnamese terminology. Maximum 200 words. Output plain text only."
        )
        try:
            return self._llm.complete(system, prompt, temperature=0.0, max_tokens=2000)
        except Exception as exc:
            logger.warning("Summary LLM failed for %s, falling back to concat: %s", entity_name, exc)
            return GRAPH_FIELD_SEP.join(descriptions)

    @staticmethod
    def _normalise_label(entity_type: str) -> str:
        normalised = entity_type.strip().replace(" ", "")
        if normalised:
            normalised = normalised[0].upper() + normalised[1:]
        known = {
            "table", "dataset", "column", "businessterm", "metric",
            "dimension", "sourceauthority", "userrole", "concept",
        }
        if normalised.lower() in known:
            return normalised
        return "Concept"

    @staticmethod
    def _estimate_tokens(texts: list[str]) -> int:
        return sum(len(t) for t in texts) // 4
