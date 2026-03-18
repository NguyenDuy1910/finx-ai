from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

from agno.workflow import Condition, Step, Workflow
from agno.workflow.types import StepInput, StepOutput

from src.knowledge.indexing.utils.models import EpisodePayload, PreparedItem
from src.knowledge.indexing.source import IndexingSource

if TYPE_CHECKING:
    from src.core.graph.client import GraphitiClient

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<(\w+)>(.*?)</\1>", re.DOTALL)

SAGA_NAME = "schema_metadata"


@dataclass
class _SchemaState:
    items: list[dict[str, Any]] = field(default_factory=list)
    episodes: list[EpisodePayload] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    items_failed: int = 0

def build_episode(payload: dict[str, Any], *, index: int = 0) -> EpisodePayload:

    name = str(payload.get("name", f"item_{index}"))

    # Shape 3: pre-built structured body with entities / relationships
    raw_body = payload.get("body")
    if isinstance(raw_body, dict):
        if "entities" in raw_body or "relationships" in raw_body:
            return {
                "name": name,
                "body": raw_body,
                "source_description": f"Schema payload: {name}",
            }

        # Shape 2: context_block string with XML tags
        context_block = raw_body.get("context_block")
        if isinstance(context_block, str):
            blocks = _parse_xml_blocks(context_block)
            return {
                "name": name,
                "body": {
                    "metadata": raw_body.get("metadata", {}),
                    "context_blocks": blocks,
                },
                "source_description": f"Schema payload: {name}",
            }

        # Shape 2b: structured facts / entity_results / user_summary
        if any(k in raw_body for k in ("facts", "entity_results", "user_summary")):
            blocks = _build_context_blocks_from_map(raw_body)
            return {
                "name": name,
                "body": {
                    "metadata": raw_body.get("metadata", {}),
                    "context_blocks": blocks,
                },
                "source_description": f"Schema payload: {name}",
            }

    # Shape 1: standard schema with columns/relationships
    database = str(payload.get("database", ""))
    description = str(payload.get("description", ""))
    columns = payload.get("columns", [])
    relationships = payload.get("relationships", [])
    domain = str(payload.get("domain", ""))

    blocks: list[dict[str, str]] = []

    # TABLE_PROFILE
    profile_lines = [f"full_name={database}.{name}" if database else f"name={name}"]
    if description:
        profile_lines.append(f"description={description}")
    if domain:
        profile_lines.append(f"domain={domain}")
    blocks.append({"name": "TABLE_PROFILE", "content": "\n".join(profile_lines)})

    # COLUMN_CATALOG
    if columns:
        col_lines = []
        for col in columns:
            parts = [str(col.get("name", ""))]
            if col.get("data_type"):
                parts.append(f"type={col['data_type']}")
            if col.get("description"):
                parts.append(f"desc={col['description']}")
            col_lines.append(" | ".join(parts))
        blocks.append({"name": "COLUMN_CATALOG", "content": "\n".join(col_lines)})

    # RELATIONSHIP_HINTS
    if relationships:
        rel_lines = []
        for rel in relationships:
            parts = []
            for key in ("source_table", "target_table", "relationship_type",
                         "source_column", "target_column"):
                val = rel.get(key)
                if val:
                    short_key = key.replace("relationship_", "")
                    parts.append(f"{short_key}={val}")
            rel_lines.append(" | ".join(parts))
        blocks.append({"name": "RELATIONSHIP_HINTS", "content": "\n".join(rel_lines)})

    return {
        "name": name,
        "body": {"metadata": {}, "context_blocks": blocks},
        "source_description": f"Schema registration for {database}.{name}" if database else name,
    }


def _parse_xml_blocks(text: str) -> list[dict[str, str]]:
    """Parse ``<TAG>content</TAG>`` pairs from a string."""
    return [
        {"name": match.group(1), "content": match.group(2).strip()}
        for match in _TAG_RE.finditer(text)
    ]


def _build_context_blocks_from_map(body: dict[str, Any]) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    mapping = {
        "facts": "FACTS",
        "entity_results": "ENTITIES",
        "user_summary": "USER_SUMMARY",
    }
    for key, block_name in mapping.items():
        value = body.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            content = "\n".join(str(v) for v in value)
        elif isinstance(value, dict):
            content = json.dumps(value)
        else:
            content = str(value)
        blocks.append({"name": block_name, "content": content})
    return blocks


class ValidateItems:
    """Step 1 -- validate raw items and store them in session state."""

    async def __call__(self, step_input: StepInput) -> StepOutput:
        state: _SchemaState = step_input.additional_data.get("state", _SchemaState())
        items = state.items

        if not items:
            state.errors.append("No items provided")
            step_input.additional_data["state"] = state
            return StepOutput(content="No items to validate", success=False)

        valid: list[dict[str, Any]] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                state.errors.append(f"item[{idx}]: not a dict")
                state.items_failed += 1
                continue
            if not item.get("name") and not item.get("body"):
                state.errors.append(f"item[{idx}]: missing 'name' and 'body'")
                state.items_failed += 1
                continue
            valid.append(item)

        state.items = valid
        step_input.additional_data["state"] = state
        return StepOutput(
            content=f"Validated {len(valid)} items",
            success=len(valid) > 0,
        )


class BuildEpisodes:
    """Step 2 -- convert validated items into Graphiti episode payloads."""

    async def __call__(self, step_input: StepInput) -> StepOutput:
        state: _SchemaState = step_input.additional_data.get("state", _SchemaState())

        episodes: list[EpisodePayload] = []
        for idx, item in enumerate(state.items):
            try:
                ep = build_episode(item, index=idx)
                episodes.append(ep)
            except Exception as exc:
                logger.error("Failed to build episode for item[%d]: %s", idx, exc)
                state.errors.append(f"item[{idx}]: {exc}")
                state.items_failed += 1

        state.episodes = episodes
        step_input.additional_data["state"] = state
        return StepOutput(content=f"Built {len(episodes)} episodes", success=len(episodes) > 0)


class WriteToGraphiti:
    """Step 3 -- persist episodes to Graphiti (bulk with single-write fallback)."""

    def __init__(self, graph: "GraphitiClient") -> None:
        self._graph = graph

    async def __call__(self, step_input: StepInput) -> StepOutput:
        state: _SchemaState = step_input.additional_data.get("state", _SchemaState())

        if not state.episodes:
            step_input.additional_data["state"] = state
            return StepOutput(content="No episodes to write", success=True)

        try:
            await self._graph.write_episodes_bulk(episodes=state.episodes, saga=SAGA_NAME)
        except Exception as bulk_err:
            logger.warning("Bulk write failed (%s), falling back to single writes", bulk_err)
            sem = asyncio.Semaphore(5)

            async def _write_one(ep: EpisodePayload) -> None:
                async with sem:
                    await self._graph.write_episode(
                        name=ep["name"],
                        body=ep["body"],
                        saga=SAGA_NAME,
                        source_description=ep.get("source_description", ep["name"]),
                    )

            results = await asyncio.gather(
                *[_write_one(ep) for ep in state.episodes], return_exceptions=True
            )
            for ep, res in zip(state.episodes, results):
                if isinstance(res, Exception):
                    state.errors.append(f"write failed for {ep.get('name', '?')}: {res}")

        step_input.additional_data["state"] = state
        return StepOutput(content="Write complete", success=not state.errors)


# ---------------------------------------------------------------------------
# Condition evaluators
# ---------------------------------------------------------------------------


def has_valid_items(step_input: StepInput) -> bool:
    state: _SchemaState = step_input.additional_data.get("state", _SchemaState())
    return len(state.items) > 0


def has_episodes(step_input: StepInput) -> bool:
    state: _SchemaState = step_input.additional_data.get("state", _SchemaState())
    return len(state.episodes) > 0


class SchemaMetadataWorkflow:

    def __init__(self, *, graph: "GraphitiClient") -> None:
        self._graph = graph
        self._write_executor = WriteToGraphiti(graph)

    @property
    def graph(self) -> "GraphitiClient":
        return self._graph

    async def run(self, items: Sequence[dict[str, Any]]) -> dict[str, Any]:
        self._graph.cost_tracker.reset()

        state = _SchemaState(items=list(items))

        workflow = Workflow(
            name="schema_metadata_indexing",
            description="Validate, build episodes, and index schema metadata into Graphiti",
            steps=[
                Step(name="Validate Items", executor=ValidateItems()),
                Condition(
                    name="Has Valid Items",
                    evaluator=has_valid_items,
                    steps=[
                        Step(name="Build Episodes", executor=BuildEpisodes()),
                        Condition(
                            name="Has Episodes",
                            evaluator=has_episodes,
                            steps=[
                                Step(name="Write to Graphiti", executor=self._write_executor),
                            ],
                        ),
                    ],
                ),
            ],
        )

        await workflow.arun(input=None, additional_data={"state": state})

        return {
            "status": "success" if state.success else "partial_failure",
            "step_results": [state.to_summary()],
        }

    # -- convenience aliases for backward compat --

    async def index_items(self, items: Sequence[dict[str, Any]]) -> dict[str, Any]:
        return await self.run(items)

    async def get_stats(
        self,
        node_labels: Sequence[str] = ("Table", "ProductArea", "DomainKnowledge", "Jargon"),
    ) -> dict[str, int]:
        stats: dict[str, int] = {}
        for label in node_labels:
            stats[f"{label.lower()}_count"] = await self._graph.count_nodes(label)
        stats["edge_count"] = await self._graph.count_edges()
        return stats

    async def get_indexed_names(self, label: str = "Table") -> set[str]:
        return await self._graph.get_node_names(label)

    async def get_indexed_tables(self) -> set[str]:
        return await self.get_indexed_names(label="Table")


# ── Concrete IndexingSource ───────────────────────────────────────────────────


class SchemaMetadataSource(IndexingSource, source_type="schema"):
    """Converts structured schema item dicts into graph episodes.

    Each item should be a dict with at minimum a ``name`` key plus any
    of: ``columns``, ``relationships``, ``description``, ``database``.

    Example::

        source = SchemaMetadataSource(items=[
            {
                "name": "fct_transactions",
                "database": "finance",
                "description": "Daily transaction fact table",
                "columns": [{"name": "amount_usd", "data_type": "DOUBLE"}],
            }
        ])
    """

    def __init__(self, items: Sequence[dict[str, Any]]) -> None:
        self._items = list(items)

    async def prepare(self) -> list[PreparedItem]:
        prepared: list[PreparedItem] = []
        for idx, item in enumerate(self._items):
            if not isinstance(item, dict):
                logger.warning("SchemaMetadataSource: item[%d] is not a dict, skipping", idx)
                continue
            if not item.get("name") and not item.get("body"):
                logger.warning("SchemaMetadataSource: item[%d] missing 'name', skipping", idx)
                continue
            try:
                episode = build_episode(item, index=idx)
                prepared.append(PreparedItem(item_name=str(item.get("name", f"item_{idx}")), episodes=[episode]))
            except Exception as exc:
                logger.error("SchemaMetadataSource: failed to build episode for item[%d]: %s", idx, exc)
        return prepared
