from __future__ import annotations

import warnings

warnings.warn(
    "IndexingWorkflow is deprecated. Use GraphPipeline from src.knowledge.graph.pipeline instead.",
    DeprecationWarning,
    stacklevel=2,
)

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agno.workflow import Condition, Step, Workflow
from agno.workflow.types import StepInput, StepOutput

from src.knowledge.indexing.source import IndexingSource
from src.knowledge.indexing.utils.models import EpisodePayload, PreparedItem

if TYPE_CHECKING:
    from src.core.graph.client import GraphitiClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared Agno Workflow step state
# ---------------------------------------------------------------------------


@dataclass
class _RunState:
    sources: list[IndexingSource]
    saga: str
    graph: "GraphitiClient"
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Step executors
# ---------------------------------------------------------------------------


class _PrepareItems:
    """Step 1 — prepare episodes from all sources (concurrent)."""

    async def __call__(self, step_input: StepInput) -> StepOutput:
        run: _RunState = step_input.additional_data["run"]

        results = await asyncio.gather(
            *[source.prepare() for source in run.sources],
            return_exceptions=True,
        )

        all_prepared: list[PreparedItem] = []
        for source, result in zip(run.sources, results):
            if isinstance(result, Exception):
                msg = f"Prepare failed [{source.__class__.__name__}]: {result}"
                run.errors.append(msg)
                logger.error(msg)
            else:
                all_prepared.extend(result)

        step_input.additional_data["prepared"] = all_prepared
        step_input.additional_data["run"] = run
        return StepOutput(
            content=f"Prepared {len(all_prepared)} item(s)",
            success=len(all_prepared) > 0,
        )


class _WriteItems:
    """Step 2 — write all prepared episodes to Graphiti (bulk-first, single fallback)."""

    async def __call__(self, step_input: StepInput) -> StepOutput:
        run: _RunState = step_input.additional_data["run"]
        prepared: list[PreparedItem] = step_input.additional_data.get("prepared", [])

        if not prepared:
            return StepOutput(content="No prepared items to write", success=True)

        all_episodes: list[EpisodePayload] = [ep for item in prepared for ep in item.episodes]

        try:
            await run.graph.write_episodes_bulk(episodes=all_episodes, saga=run.saga)
        except Exception as bulk_err:
            logger.warning("Bulk write failed (%s), falling back to single writes", bulk_err)
            sem = asyncio.Semaphore(5)

            async def _write_one(ep: EpisodePayload) -> None:
                async with sem:
                    await run.graph.write_episode(
                        name=ep["name"],
                        body=ep["body"],
                        saga=run.saga,
                        source_description=ep.get("source_description", ep["name"]),
                    )

            write_results = await asyncio.gather(
                *[_write_one(ep) for ep in all_episodes], return_exceptions=True
            )
            for ep, res in zip(all_episodes, write_results):
                if isinstance(res, Exception):
                    run.errors.append(f"write failed for {ep.get('name', '?')}: {res}")

        step_input.additional_data["run"] = run
        return StepOutput(content="Write complete", success=not run.errors)


# ---------------------------------------------------------------------------
# Condition
# ---------------------------------------------------------------------------


def _has_prepared_items(step_input: StepInput) -> bool:
    return len(step_input.additional_data.get("prepared", [])) > 0


# ---------------------------------------------------------------------------
# Public workflow
# ---------------------------------------------------------------------------


class IndexingWorkflow:
    """Generic indexing orchestrator — drives any ``IndexingSource`` into Graphiti.

    Sources are prepared concurrently (Step 1) then written with bulk-first
    fallback (Step 2). Add new data sources by creating a new ``IndexingSource``
    subclass and passing it here.

    Example::

        wf = IndexingWorkflow(client=graphiti_client)
        await wf.arun(
            sources=[
                SchemaMetadataSource(items=[...]),
                TextSource(texts=[("kyc_rules", "KYC stores customer identity...")]),
                DocumentSource(requests=[IngestionRequest(...)]),
            ]
        )
    """

    def __init__(self, client: "GraphitiClient") -> None:
        self._client = client

    async def arun(self, sources: list[IndexingSource], saga: str = "indexing") -> None:
        run = _RunState(sources=sources, saga=saga, graph=self._client)

        workflow = Workflow(
            name="multi_source_indexing",
            steps=[
                Step(name="Prepare Items", executor=_PrepareItems()),
                Condition(
                    name="Has Prepared Items",
                    evaluator=_has_prepared_items,
                    steps=[Step(name="Write Items", executor=_WriteItems())],
                ),
            ],
        )

        await workflow.arun(input=None, additional_data={"run": run, "prepared": []})

        if run.errors:
            for err in run.errors:
                logger.warning(err)


# ---------------------------------------------------------------------------
# TextSource — simplest source (no LLM, wrap text directly as episodes)
# ---------------------------------------------------------------------------


class TextSource(IndexingSource, source_type="text"):
    """Wraps raw text strings as Graphiti text episodes.

    No LLM extraction — use this for pre-structured content (glossaries,
    KYC rules, product definitions) that is already clean and needs no
    entity/relationship extraction.

    Args:
        texts: list of ``(name, text)`` tuples to index.
        source_description: optional label applied to all episodes.

    Example::

        TextSource(texts=[
            ("kyc_rules", "KYC table stores customer identity verification records..."),
            ("product_glossary", "Gross Bookings = total value of transactions..."),
        ])
    """

    def __init__(
        self,
        texts: list[tuple[str, str]],
        *,
        source_description: str = "raw_text_ingestion",
    ) -> None:
        self._texts = texts
        self._source_description = source_description

    async def prepare(self) -> list[PreparedItem]:
        prepared: list[PreparedItem] = []
        for name, text in self._texts:
            if not text.strip():
                logger.warning("TextSource: empty text for %r, skipping", name)
                continue
            episode: EpisodePayload = {
                "name": name,
                "body": text,
                "source_description": self._source_description,
            }
            prepared.append(PreparedItem(item_name=name, episodes=[episode]))
        return prepared
