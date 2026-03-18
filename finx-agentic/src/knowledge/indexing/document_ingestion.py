from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Optional

from agno.workflow import Condition, Step, Workflow
from agno.workflow.types import StepInput, StepOutput

from src.knowledge.indexing.source import IndexingSource
from src.knowledge.indexing.payload import CanonicalEvent
from src.knowledge.indexing.utils import (
    EpisodePayload,
    IngestionInputType,
    IngestionRequest,
    IngestionState,
    PreparedEpisode,
    PreparedItem,
    SourceSection,
    build_extraction_agent,
    event_to_episode,
    infer_route,
    normalize_event,
    normalize_source_type,
    parse_event_batch,
    read_request_text,
    resolve_source_name,
    slugify,
    split_sections,
    utc_now,
)

if TYPE_CHECKING:
    from src.core.graph.client import GraphitiClient

logger = logging.getLogger(__name__)

SAGA_NAME = "document_ingestion"
_ROUTES = ("semantic", "physical", "query", "governance", "feedback")



def _get_state(step_input: StepInput, group_id: str = "finx_knowledge") -> IngestionState:
    return step_input.additional_data.get(
        "state",
        IngestionState(requests=[], group_id=group_id),
    )


class ReadDocuments:

    def __init__(self, *, max_section_chars: int = 6000) -> None:
        self._max_section_chars = max_section_chars

    async def __call__(self, step_input: StepInput) -> StepOutput:
        state = _get_state(step_input)
        requests = step_input.additional_data.get("requests", state.requests)

        if not requests:
            state.errors.append("No ingestion requests provided")
            step_input.additional_data["state"] = state
            return StepOutput(content="No requests", success=False)

        for index, request in enumerate(requests):
            try:
                self._process_request(index, request, state)
            except Exception as exc:
                state.errors.append(f"document_reader[{index}] failed: {exc}")

        step_input.additional_data["state"] = state
        return StepOutput(
            content=f"Produced {len(state.sections)} sections",
            success=len(state.sections) > 0,
        )

    def _process_request(
        self, index: int, request: IngestionRequest, state: IngestionState
    ) -> None:
        source_name = resolve_source_name(index, request)
        source_record_id = slugify(source_name)
        source_type = normalize_source_type(request.source_type)
        source_description = f"Document ingestion from {source_name}"

        raw_text = read_request_text(request)
        if not raw_text.strip():
            raise ValueError("No text extracted from source")

        sections = split_sections(raw_text, max_chars=self._max_section_chars)
        if not sections:
            raise ValueError("No semantic sections produced")

        reference_time = utc_now()

        for section_index, section_text in enumerate(sections, start=1):
            metadata = {
                "source_index": index,
                "source_name": source_name,
                "source_record_id": source_record_id,
                "source_type": source_type,
                "section_index": section_index,
                "entity_name": request.entity_name,
                "tags": list(request.tags),
            }
            metadata.update(request.extra_metadata)

            state.sections.append(
                SourceSection(
                    source_index=index,
                    source_name=source_name,
                    source_record_id=source_record_id,
                    source_type=source_type,
                    source_description=source_description,
                    reference_time=reference_time,
                    section_index=section_index,
                    section_text=section_text,
                    entity_name=request.entity_name,
                    tags=list(request.tags),
                    metadata=metadata,
                )
            )
            state.knowledge_sources.append({
                "source_type": source_type,
                "source_name": source_name,
                "section_index": section_index,
                "content": section_text,
            })


class EnrichSections:

    def __init__(self, agents: dict[str, Any]) -> None:
        self._agents = agents

    async def __call__(self, step_input: StepInput) -> StepOutput:
        state = _get_state(step_input)

        if not state.sections:
            step_input.additional_data["state"] = state
            return StepOutput(content="No sections to enrich", success=True)

        extracted: list[CanonicalEvent] = []

        for section in state.sections:
            route = infer_route(section.section_text)
            agent = self._agents.get(route) or self._agents["semantic"]
            prompt = _build_extraction_prompt(section, state)

            try:
                result = agent.run(json.dumps(prompt, ensure_ascii=False))
                events, errors = parse_event_batch(result)
                state.errors.extend(errors)
                for event in events:
                    normalize_event(event, section, state)
                    extracted.append(event)
            except Exception as exc:
                state.errors.append(
                    f"enrich[{section.source_name}:{section.section_index}] failed: {exc}"
                )

        state.extracted_events = extracted
        state.prepared_episodes = [event_to_episode(e) for e in extracted]

        step_input.additional_data["state"] = state
        return StepOutput(
            content=f"Prepared {len(state.prepared_episodes)} episodes",
            success=len(state.prepared_episodes) > 0 or not state.errors,
        )


def _build_extraction_prompt(section: SourceSection, state: IngestionState) -> dict[str, Any]:
    return {
        "group_id": state.group_id,
        "source_system": state.source_system,
        "source_record_id": section.source_record_id,
        "source_description": section.source_description,
        "reference_time": section.reference_time.isoformat(),
        "source_name": section.source_name,
        "source_type": section.source_type,
        "section_index": section.section_index,
        "section_text": section.section_text,
        "entity_name": section.entity_name,
        "tags": section.tags,
    }


class WriteEpisodes:

    def __init__(self, graph: "GraphitiClient") -> None:
        self._graph = graph

    async def __call__(self, step_input: StepInput) -> StepOutput:
        state = _get_state(step_input)
        write_enabled = bool(step_input.additional_data.get("write_to_graph", True))

        if not write_enabled:
            step_input.additional_data["state"] = state
            return StepOutput(content="Graph write disabled", success=True)

        if not state.prepared_episodes:
            step_input.additional_data["state"] = state
            return StepOutput(content="No episodes to write", success=True)

        for episode in state.prepared_episodes:
            try:
                await self._graph.write_episode(
                    name=episode.name,
                    body=episode.episode_body,
                    saga=SAGA_NAME,
                    source_description=episode.source_description,
                )
            except Exception as exc:
                state.errors.append(f"writer failed for {episode.name}: {exc}")

        step_input.additional_data["state"] = state
        return StepOutput(
            content="Write complete",
            success=not state.errors,
        )



def has_sections(step_input: StepInput) -> bool:
    state = _get_state(step_input)
    return len(state.sections) > 0


def has_episodes(step_input: StepInput) -> bool:
    state = _get_state(step_input)
    return len(state.prepared_episodes) > 0



class DocumentIngestionWorkflow:

    def __init__(
        self,
        *,
        graph: "GraphitiClient",
        group_id: str = "finx_knowledge",
        model_id: str = "gpt-4.1-mini",
        max_section_chars: int = 6000,
        agents: Optional[dict[str, Any]] = None,
    ) -> None:
        self._graph = graph
        self._group_id = group_id
        self._agents = agents or {r: build_extraction_agent(model_id, route=r) for r in _ROUTES}
        self._reader = ReadDocuments(max_section_chars=max_section_chars)
        self._enricher = EnrichSections(self._agents)
        self._writer_step = WriteEpisodes(graph)

    async def run(
        self,
        requests: list[IngestionRequest],
        *,
        write_to_graph: bool = True,
    ) -> dict[str, Any]:
        state = IngestionState(requests=list(requests), group_id=self._group_id)

        workflow = Workflow(
            name="document_ingestion",
            description="Read, enrich, and index multi-source documents into Graphiti",
            steps=[
                Step(name="Read Documents", executor=self._reader),
                Condition(
                    name="Has Sections",
                    evaluator=has_sections,
                    steps=[
                        Step(name="Enrich Sections", executor=self._enricher),
                        Condition(
                            name="Has Episodes",
                            evaluator=has_episodes,
                            steps=[
                                Step(name="Write Episodes", executor=self._writer_step),
                            ],
                        ),
                    ],
                ),
            ],
        )

        await workflow.arun(
            input=None,
            additional_data={
                "state": state,
                "requests": list(requests),
                "write_to_graph": write_to_graph,
            },
        )

        if state.errors:
            logger.warning("DocumentIngestionWorkflow finished with %d error(s)", len(state.errors))
            for err in state.errors:
                logger.warning("  - %s", err)

        return {
            "status": "success" if not state.errors else "partial_failure",
            "knowledge_sources": state.knowledge_sources,
        }

    async def ingest(
        self,
        requests: list[IngestionRequest],
        *,
        write_to_graph: bool = True,
    ) -> dict[str, Any]:
        return await self.run(requests=requests, write_to_graph=write_to_graph)

    async def ingest_file(
        self,
        raw_bytes: bytes,
        filename: str,
        *,
        content_type: str = "",
        entity_name: str = "",
        tags: Optional[list[str]] = None,
        chunking_strategy: Any = None,
        write_to_graph: bool = True,
    ) -> dict[str, Any]:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        source_type = "pdf_extract" if ext == "pdf" else "raw_text"

        request = IngestionRequest(
            input_type=IngestionInputType.FILE_BYTES,
            source_type=source_type,
            source_name=filename,
            content_bytes=raw_bytes,
            filename=filename,
            content_type=content_type,
            entity_name=entity_name,
            tags=tags or [],
            chunking_strategy=chunking_strategy,
        )
        return await self.run([request], write_to_graph=write_to_graph)

    async def ingest_url(
        self,
        url: str,
        *,
        entity_name: str = "",
        tags: Optional[list[str]] = None,
        confluence_base_url: Optional[str] = None,
        confluence_username: Optional[str] = None,
        confluence_api_token: Optional[str] = None,
        chunking_strategy: Any = None,
        write_to_graph: bool = True,
    ) -> dict[str, Any]:
        from src.knowledge.indexing.utils.doc_parser import _is_confluence_url

        is_confluence = _is_confluence_url(url)

        request = IngestionRequest(
            input_type=IngestionInputType.CONFLUENCE if is_confluence else IngestionInputType.URL,
            source_type="confluence_page" if is_confluence else "url_content",
            source_name=url,
            url=url,
            confluence_base_url=confluence_base_url,
            confluence_username=confluence_username,
            confluence_api_token=confluence_api_token,
            entity_name=entity_name,
            tags=tags or [],
            chunking_strategy=chunking_strategy,
        )
        return await self.run([request], write_to_graph=write_to_graph)

    async def ingest_text(
        self,
        text: str,
        *,
        source_name: str = "",
        entity_name: str = "",
        tags: Optional[list[str]] = None,
        chunking_strategy: Any = None,
        write_to_graph: bool = True,
    ) -> dict[str, Any]:
        request = IngestionRequest(
            input_type=IngestionInputType.TEXT,
            source_type="raw_text",
            source_name=source_name,
            content_text=text,
            entity_name=entity_name,
            tags=tags or [],
            chunking_strategy=chunking_strategy,
        )
        return await self.run([request], write_to_graph=write_to_graph)


# ── Concrete IndexingSource ───────────────────────────────────────────────────


class DocumentSource(IndexingSource, source_type="document"):
    """IndexingSource adapter for documents (PDF, URL, Confluence, raw text).

    Example::

        source = DocumentSource(
            requests=[
                IngestionRequest(input_type=IngestionInputType.FILE_BYTES, content_bytes=pdf_bytes, filename="spec.pdf"),
                IngestionRequest(input_type=IngestionInputType.URL, url="https://confluence.example.com/page/123"),
            ]
        )
    """

    def __init__(
        self,
        requests: list[IngestionRequest],
        *,
        group_id: str = "finx_knowledge",
        model_id: str = "gpt-4.1-mini",
        max_section_chars: int = 6000,
        agents: Optional[dict[str, Any]] = None,
    ) -> None:
        self._workflow = DocumentIngestionWorkflow(
            graph=None,  # type: ignore[arg-type]  # not needed for prepare-only path
            group_id=group_id,
            model_id=model_id,
            max_section_chars=max_section_chars,
            agents=agents,
        )
        self._requests = requests

    async def prepare(self) -> list[PreparedItem]:
        state = IngestionState(requests=self._requests, group_id=self._workflow._group_id)

        for index, request in enumerate(self._requests):
            try:
                self._workflow._reader._process_request(index, request, state)
            except Exception as exc:
                state.errors.append(f"document_reader[{index}] failed: {exc}")
                logger.error("DocumentSource read failed for request[%d]: %s", index, exc)

        if not state.sections:
            logger.warning("DocumentSource: no sections from %d request(s)", len(self._requests))
            return []

        for section in state.sections:
            route = infer_route(section.section_text)
            agent = self._workflow._enricher._agents.get(route) or self._workflow._enricher._agents["semantic"]
            try:
                result = agent.run(json.dumps(_build_extraction_prompt(section, state), ensure_ascii=False))
                events, errors = parse_event_batch(result)
                state.errors.extend(errors)
                for event in events:
                    normalize_event(event, section, state)
                    state.extracted_events.append(event)
            except Exception as exc:
                state.errors.append(f"enrich[{section.source_name}:{section.section_index}] failed: {exc}")

        state.prepared_episodes = [event_to_episode(e) for e in state.extracted_events]

        return [
            PreparedItem(
                item_name=ep.name,
                episodes=[{"name": ep.name, "body": ep.episode_body, "source_description": ep.source_description}],
            )
            for ep in state.prepared_episodes
        ]

