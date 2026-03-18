"""Event extraction utilities — route inference, prompt building, agent factory, event normalisation."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from src.knowledge.indexing.payload import (
    CanonicalEvent,
    CanonicalEventBatch,
    EpisodeSourceType,
)

if TYPE_CHECKING:
    from src.knowledge.indexing.utils.models import IngestionRequest, IngestionState, PreparedEpisode, SourceSection

logger = logging.getLogger(__name__)

_ROUTES = ("semantic", "physical", "query", "governance", "feedback")

_ROUTE_INSTRUCTIONS: dict[str, str] = {
    "semantic": "\nFocus on: metric_defined, metric_definition_updated, term_alias_curated\n",
    "physical": "\nFocus on: table_mapping_curated, column_mapping_curated, authoritative_source_assigned, join_path_curated\n",
    "query": "\nFocus on: query_pattern_approved, validation_rule_added, unsafe_pattern_banned\n",
    "governance": "\nFocus on: access_policy_updated, sensitivity_labeled, freshness_policy_updated\n",
    "feedback": "\nFocus on: analyst_feedback_received, mapping_corrected, failure_case_recorded\n",
}

_BASE_PROMPT = """\
You extract Graphiti-ready canonical events from enterprise finance and analytics documents.

Rules:
- Output ONLY valid structured data for CanonicalEventBatch.
- Each event must be atomic: one coherent truth update per event.
- Prefer stable canonical IDs like:
  metric:gross_bookings  term:gb  dimension:region
  table:finance.fct_gross_bookings_daily
  column:finance.fct_gross_bookings_daily.gross_bookings_usd
  policy:finance_restricted  pattern:metric_by_region_quarter_v1
- Preserve evidence_text only when useful and keep it short.
- Do not invent facts not supported by the text.
- Use JSON episodes mindset: compact, structured, provenance-friendly.
- Use the provided group_id, source_system, source_record_id, and reference_time.
- If there are no meaningful events, return {"events": []}."""


def infer_route(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ("policy", "access", "rbac", "restricted", "sensitivity")):
        return "governance"
    if any(w in lower for w in ("sql", "query", "select ", "join ", "group by", "template")):
        return "query"
    if any(w in lower for w in ("table", "column", "schema", "warehouse", "grain", "dataset")):
        return "physical"
    if any(w in lower for w in ("feedback", "incorrect", "correct mapping", "fix", "review")):
        return "feedback"
    return "semantic"


def build_system_prompt(route: str) -> str:
    return f"{_BASE_PROMPT}\n{_ROUTE_INSTRUCTIONS.get(route, '')}".strip()


def normalize_source_type(value: Any) -> str:
    if value is None:
        return "raw_text"
    if hasattr(value, "value"):
        return str(getattr(value, "value"))
    return str(value)


def normalize_episode_source(value: str) -> EpisodeSourceType:
    lowered = value.lower()
    if lowered in {"raw_text", "text", "txt", "md", "rst"}:
        return "text"
    if lowered in {"message", "chat"}:
        return "message"
    return "json"


def resolve_source_name(index: int, request: IngestionRequest) -> str:
    return request.source_name or request.filename or request.url or f"source_{index + 1}"


def build_extraction_agent(model_id: str, *, route: str) -> Any:
    from agno.agent import Agent
    from agno.models.openai import OpenAIResponses

    return Agent(
        model=OpenAIResponses(id=model_id),
        instructions=build_system_prompt(route),
        output_schema=CanonicalEventBatch,
        structured_outputs=True,
        markdown=False,
    )


def parse_event_batch(result: Any) -> tuple[list[CanonicalEvent], list[str]]:
    content = getattr(result, "content", result)
    if isinstance(content, CanonicalEventBatch):
        return content.events, []
    try:
        if isinstance(content, dict):
            return CanonicalEventBatch.model_validate(content).events, []
        return CanonicalEventBatch.model_validate_json(str(content)).events, []
    except ValidationError as exc:
        return [], [f"structured extraction validation failed: {exc}"]


def normalize_event(event: CanonicalEvent, section: SourceSection, state: IngestionState) -> None:
    event.group_id = state.group_id
    event.source_system = event.source_system or state.source_system
    event.source_record_id = event.source_record_id or section.source_record_id
    event.source_description = event.source_description or section.source_description
    event.reference_time = event.reference_time or section.reference_time
    event.source_type = normalize_episode_source(
        event.source_type if event.source_type else section.source_type
    )
    if not event.tags:
        event.tags = list(section.tags)


def event_to_episode(event: CanonicalEvent) -> PreparedEpisode:
    from src.knowledge.indexing.utils.models import PreparedEpisode

    body = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "event_version": event.event_version,
        "group_id": event.group_id,
        "reference_time": event.reference_time.isoformat(),
        "source_system": event.source_system,
        "source_record_id": event.source_record_id,
        "source_type": event.source_type,
        "source_description": event.source_description,
        "authority_score": event.authority_score,
        "confidence_score": event.confidence_score,
        "tags": event.tags,
        "payload": event.payload.model_dump(),
    }
    return PreparedEpisode(
        name=event.event_type,
        episode_body=body,
        source=event.source_type,
        source_description=event.source_description,
        reference_time=event.reference_time,
        group_id=event.group_id,
    )
