import asyncio
import json
from types import SimpleNamespace
from typing import Any

from src.knowledge.indexing.document_ingestion import (
    CanonicalEvent,
    CanonicalEventBatch,
    DocumentIngestionWorkflow,
    IngestionInputType,
    IngestionRequest,
    MetricDefinitionPayload,
)


class _Snapshot:
    def model_dump(self) -> dict[str, Any]:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "embedding_tokens": 0,
            "llm_calls": 0,
            "embedding_calls": 0,
            "cost_usd": 0.0,
            "breakdown": {},
        }


class _Tracker:
    def __init__(self) -> None:
        self.reset_calls = 0

    def reset(self) -> None:
        self.reset_calls += 1

    def snapshot(self) -> _Snapshot:
        return _Snapshot()


class _FakeGraph:
    def __init__(self, fail_on: set[int] | None = None) -> None:
        self.fail_on = fail_on or set()
        self.calls: list[dict[str, Any]] = []
        self._idx = 0
        self.cost_tracker = _Tracker()

    async def add_episode(
        self,
        *,
        name: str,
        episode_body: dict[str, Any] | str,
        source: str,
        source_description: str,
        reference_time,
        group_id: str,
        entity_types=None,
        edge_types=None,
        edge_type_map=None,
    ) -> Any:
        current = self._idx
        self._idx += 1
        if current in self.fail_on:
            raise RuntimeError("forced writer failure")

        call = {
            "name": name,
            "episode_body": episode_body,
            "source": source,
            "source_description": source_description,
            "reference_time": reference_time,
            "group_id": group_id,
        }
        self.calls.append(call)
        return {"episode_id": f"ep-{current}", "nodes": 1, "edges": 1}


class _FakeAgent:
    def __init__(self, callback) -> None:
        self._callback = callback

    def run(self, input: Any, **kwargs: Any) -> Any:
        payload = json.loads(input) if isinstance(input, str) else input
        return SimpleNamespace(content=self._callback(payload))


def _build_agents(callback) -> dict[str, _FakeAgent]:
    agent = _FakeAgent(callback)
    return {
        "semantic": agent,
        "physical": agent,
        "query": agent,
        "governance": agent,
        "feedback": agent,
    }


def _build_metric_event(payload: dict[str, Any]) -> CanonicalEvent:
    return CanonicalEvent(
        event_type="metric_defined",
        group_id="placeholder",
        reference_time="2026-01-01T00:00:00Z",
        source_system="extractor",
        source_record_id=payload.get("source_record_id", "src"),
        source_description=payload.get("source_description", "desc"),
        payload=MetricDefinitionPayload(
            metric_id=payload["metric_id"],
            metric_name=payload.get("metric_name", "Metric"),
            definition=payload.get("definition", "Definition"),
        ),
    )


def test_multi_source_read_provenance() -> None:
    graph = _FakeGraph()
    workflow = DocumentIngestionWorkflow(
        graph=graph,
        group_id="gid",
        max_section_chars=12,
        agents=_build_agents(lambda _prompt: CanonicalEventBatch(events=[])),
    )

    requests = [
        IngestionRequest(
            input_type=IngestionInputType.TEXT,
            source_name="source_a",
            content_text="alpha alpha alpha\n\nbeta beta beta",
        ),
        IngestionRequest(
            input_type=IngestionInputType.TEXT,
            source_name="source_b",
            content_text="one one one\n\ntwo two two",
        ),
    ]

    result = asyncio.run(workflow.run(requests, write_to_graph=False))

    summary = result["summary"]
    assert summary["items_processed"] == 2
    assert summary["chunks_produced"] == 4
    assert len(result["knowledge_sources"]) == 4
    assert result["knowledge_sources"][0]["source_name"] == "source_a"
    assert result["knowledge_sources"][2]["source_name"] == "source_b"
    assert graph.cost_tracker.reset_calls == 1


def test_strict_schema_validation_error_is_reported() -> None:
    graph = _FakeGraph()

    def bad_output(_prompt: dict[str, Any]) -> dict[str, Any]:
        return {
            "events": [
                {
                    "event_type": "metric_defined",
                    "group_id": "gid",
                    "reference_time": "2026-01-01T00:00:00Z",
                    "source_system": "extractor",
                    "source_record_id": "s1",
                    "source_description": "d1",
                    "payload": {
                        "metric_id": "metric:revenue",
                        "metric_name": "Revenue",
                        "definition": "Gross revenue",
                        "unexpected": "not_allowed",
                    },
                }
            ]
        }

    workflow = DocumentIngestionWorkflow(
        graph=graph,
        group_id="gid",
        agents=_build_agents(bad_output),
    )

    requests = [
        IngestionRequest(
            input_type=IngestionInputType.TEXT,
            source_name="schema_note",
            content_text="Revenue means top-line amount",
        )
    ]

    result = asyncio.run(workflow.run(requests, write_to_graph=False))

    assert result["status"] == "partial_failure"
    assert result["summary"]["episodes_written"] == 0
    assert any("structured extraction validation failed" in err for err in result["summary"]["errors"])


def test_order_is_preserved_by_source_and_section() -> None:
    graph = _FakeGraph()

    def ordered_output(prompt: dict[str, Any]) -> CanonicalEventBatch:
        source_name = prompt["source_name"]
        section_index = prompt["section_index"]
        event = _build_metric_event(
            {
                "metric_id": f"metric:{source_name}:{section_index}",
                "metric_name": f"{source_name}:{section_index}",
                "definition": "def",
                "source_record_id": prompt["source_record_id"],
                "source_description": prompt["source_description"],
            }
        )
        return CanonicalEventBatch(events=[event])

    workflow = DocumentIngestionWorkflow(
        graph=graph,
        group_id="gid",
        max_section_chars=12,
        agents=_build_agents(ordered_output),
    )

    requests = [
        IngestionRequest(
            input_type=IngestionInputType.TEXT,
            source_name="a",
            content_text="aa aa aa\n\nbb bb bb",
        ),
        IngestionRequest(
            input_type=IngestionInputType.TEXT,
            source_name="b",
            content_text="cc cc cc\n\ndd dd dd",
        ),
    ]

    asyncio.run(workflow.run(requests, write_to_graph=True))

    metric_ids = [call["episode_body"]["payload"]["metric_id"] for call in graph.calls]
    assert metric_ids == [
        "metric:a:1",
        "metric:a:2",
        "metric:b:1",
        "metric:b:2",
    ]


def test_writer_builds_canonical_event_envelope() -> None:
    graph = _FakeGraph()

    def one_event(prompt: dict[str, Any]) -> CanonicalEventBatch:
        return CanonicalEventBatch(
            events=[
                _build_metric_event(
                    {
                        "metric_id": "metric:bookings",
                        "metric_name": "Gross Bookings",
                        "definition": "sum before refunds",
                        "source_record_id": prompt["source_record_id"],
                        "source_description": prompt["source_description"],
                    }
                )
            ]
        )

    workflow = DocumentIngestionWorkflow(
        graph=graph,
        group_id="gid",
        agents=_build_agents(one_event),
    )

    requests = [
        IngestionRequest(
            input_type=IngestionInputType.TEXT,
            source_name="glossary",
            content_text="Gross Bookings is total booking value",
        )
    ]

    result = asyncio.run(workflow.run(requests, write_to_graph=True))

    assert result["summary"]["episodes_written"] == 1
    body = graph.calls[0]["episode_body"]
    assert body["event_type"] == "metric_defined"
    assert body["event_version"] == "v1"
    assert body["group_id"] == "gid"
    assert "reference_time" in body
    assert body["source_record_id"] == "glossary"
    assert body["payload"]["metric_id"] == "metric:bookings"


def test_partial_failure_does_not_abort_writes() -> None:
    graph = _FakeGraph(fail_on={1})

    def two_sections(prompt: dict[str, Any]) -> CanonicalEventBatch:
        section_index = prompt["section_index"]
        return CanonicalEventBatch(
            events=[
                _build_metric_event(
                    {
                        "metric_id": f"metric:sec:{section_index}",
                        "source_record_id": prompt["source_record_id"],
                        "source_description": prompt["source_description"],
                    }
                )
            ]
        )

    workflow = DocumentIngestionWorkflow(
        graph=graph,
        group_id="gid",
        max_section_chars=24,
        agents=_build_agents(two_sections),
    )

    requests = [
        IngestionRequest(
            input_type=IngestionInputType.TEXT,
            source_name="s1",
            content_text="first chunk text\n\nsecond chunk text",
        )
    ]

    result = asyncio.run(workflow.run(requests, write_to_graph=True))

    assert result["status"] == "partial_failure"
    assert result["summary"]["episodes_written"] == 1
    assert any("writer failed" in err for err in result["summary"]["errors"])


def test_duplicates_are_retained_across_sources() -> None:
    graph = _FakeGraph()

    def duplicate_event(_prompt: dict[str, Any]) -> CanonicalEventBatch:
        return CanonicalEventBatch(
            events=[
                _build_metric_event(
                    {
                        "metric_id": "metric:duplicate",
                        "metric_name": "Duplicate",
                        "definition": "same payload every time",
                        "source_record_id": "same-record",
                        "source_description": "same-desc",
                    }
                )
            ]
        )

    workflow = DocumentIngestionWorkflow(
        graph=graph,
        group_id="gid",
        agents=_build_agents(duplicate_event),
    )

    requests = [
        IngestionRequest(
            input_type=IngestionInputType.TEXT,
            source_name="source_1",
            content_text="dup event source one",
        ),
        IngestionRequest(
            input_type=IngestionInputType.TEXT,
            source_name="source_2",
            content_text="dup event source two",
        ),
    ]

    result = asyncio.run(workflow.run(requests, write_to_graph=True))

    assert result["summary"]["episodes_written"] == 2
    assert len(graph.calls) == 2
    payloads = [call["episode_body"]["payload"]["metric_id"] for call in graph.calls]
    assert payloads == ["metric:duplicate", "metric:duplicate"]
