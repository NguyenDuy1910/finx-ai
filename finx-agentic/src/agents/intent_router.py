from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from agno.agent import Agent, RunOutput

from src.core.intent import (
    IntentClassification,
    RouterContext,
    RouterResult,
    UserIntent,
)
from src.core.model_factory import create_model
from src.core.types import (
    GeneratedSQL,
    ParsedQuery,
    SchemaContext,
    Text2SQLResult,
    ValidationResult,
)
from src.prompts.manager import get_prompt_manager
from src.tools.graph_tools import GraphSearchTools

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.7

_INTENT_MAP = {
    "data_query": UserIntent.DATA_QUERY,
    "schema_exploration": UserIntent.SCHEMA_EXPLORATION,
    "relationship_discovery": UserIntent.RELATIONSHIP_DISCOVERY,
    "knowledge_lookup": UserIntent.KNOWLEDGE_LOOKUP,
    "feedback": UserIntent.FEEDBACK,
    "clarification": UserIntent.CLARIFICATION,
    "general": UserIntent.GENERAL,
}

_CONTEXT_INTENTS = {
    UserIntent.DATA_QUERY,
    UserIntent.SCHEMA_EXPLORATION,
    UserIntent.RELATIONSHIP_DISCOVERY,
    UserIntent.KNOWLEDGE_LOOKUP,
}


def _create_classifier() -> Agent:
    pm = get_prompt_manager()
    instructions = pm.render("router/classify.jinja2")
    return Agent(
        name="IntentClassifier",
        model=create_model(),
        instructions=[instructions],
        output_schema=IntentClassification,
        markdown=False,
    )


def classify_intent(
    message: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    available_databases: Optional[List[str]] = None,
) -> IntentClassification:
    pm = get_prompt_manager()
    prompt = pm.render(
        "router/classify_prompt.jinja2",
        message=message,
        conversation_history=conversation_history or [],
        available_databases=available_databases or [],
    )
    agent = _create_classifier()
    response: RunOutput = agent.run(prompt, output_schema=IntentClassification)

    if response and response.content:
        if isinstance(response.content, IntentClassification):
            return response.content
        try:
            return IntentClassification.model_validate_json(str(response.content))
        except Exception:
            pass

    try:
        raw = str(response.content) if response else ""
        data = json.loads(raw)
        intent_str = data.get("intent", "general")
        return IntentClassification(
            intent=_INTENT_MAP.get(intent_str, UserIntent.GENERAL),
            confidence=float(data.get("confidence", 0.5)),
            entities=data.get("entities", []),
            database=data.get("database"),
            requires_graph_context=data.get("requires_graph_context", False),
            reasoning=data.get("reasoning", ""),
        )
    except Exception:
        logger.warning("Failed to parse intent classification, defaulting to GENERAL")
        return IntentClassification(intent=UserIntent.GENERAL, confidence=0.3)


def fetch_graph_context(
    intent: IntentClassification,
    message: str,
    graph_tools: GraphSearchTools,
) -> Dict[str, Any]:
    context: Dict[str, Any] = {}

    if intent.intent == UserIntent.SCHEMA_EXPLORATION:
        context["schema"] = json.loads(
            graph_tools.search_schema(message, intent.database)
        )
        for entity in intent.entities[:3]:
            details = graph_tools.get_table_details(entity, intent.database)
            parsed = json.loads(details)
            if parsed.get("table"):
                context.setdefault("table_details", {})[entity] = parsed

    elif intent.intent == UserIntent.RELATIONSHIP_DISCOVERY:
        entities = intent.entities
        if len(entities) >= 2:
            context["join_path"] = json.loads(
                graph_tools.find_join_path(entities[0], entities[1], intent.database)
            )
        for entity in entities[:3]:
            context.setdefault("related", {})[entity] = json.loads(
                graph_tools.find_related_tables(entity, intent.database)
            )

    elif intent.intent == UserIntent.DATA_QUERY:
        context["schema"] = json.loads(
            graph_tools.search_schema(message, intent.database)
        )
        context["patterns"] = json.loads(
            graph_tools.get_query_patterns(message)
        )

    elif intent.intent == UserIntent.KNOWLEDGE_LOOKUP:
        context["similar_queries"] = json.loads(
            graph_tools.get_similar_queries(message, top_k=5)
        )
        context["patterns"] = json.loads(
            graph_tools.get_query_patterns(message)
        )
        for entity in intent.entities[:3]:
            resolved = json.loads(graph_tools.resolve_business_term(entity))
            if resolved:
                context.setdefault("resolved_terms", {})[entity] = resolved

    return context


def _needs_clarification(intent: IntentClassification) -> bool:
    if intent.ambiguous:
        return True
    if intent.confidence < CONFIDENCE_THRESHOLD:
        return True
    if intent.missing_info:
        return True
    if intent.intent == UserIntent.DATA_QUERY and not intent.entities:
        return True
    if intent.intent == UserIntent.RELATIONSHIP_DISCOVERY and len(intent.entities) < 1:
        return True
    return False


def _gather_graph_hints(
    intent: IntentClassification,
    message: str,
    graph_tools: GraphSearchTools,
) -> List[str]:
    hints: List[str] = []
    try:
        raw = graph_tools.search_schema(message, intent.database)
        data = json.loads(raw)
        for t in data.get("tables", [])[:5]:
            name = t.get("name", "")
            summary = t.get("summary", "")
            if name:
                hints.append(f"Table: {name}" + (f" - {summary}" if summary else ""))
        for e in data.get("entities", [])[:5]:
            name = e.get("name", "")
            summary = e.get("summary", "")
            if name:
                hints.append(f"Entity: {name}" + (f" - {summary}" if summary else ""))
    except Exception:
        pass
    return hints


def _generate_clarification(
    message: str,
    intent: IntentClassification,
    graph_hints: List[str],
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    pm = get_prompt_manager()
    instructions = pm.render("router/clarify.jinja2")
    prompt = pm.render(
        "router/clarify_prompt.jinja2",
        message=message,
        intent=intent,
        graph_hints=graph_hints,
        conversation_history=conversation_history or [],
    )
    agent = Agent(
        name="Clarifier",
        model=create_model(),
        instructions=[instructions],
        markdown=True,
    )
    response: RunOutput = agent.run(prompt)
    return str(response.content) if response and response.content else ""


def _respond_with_context(
    message: str,
    intent: UserIntent,
    context: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    pm = get_prompt_manager()

    template_map = {
        UserIntent.SCHEMA_EXPLORATION: "router/schema_response.jinja2",
        UserIntent.RELATIONSHIP_DISCOVERY: "router/relationship_response.jinja2",
        UserIntent.KNOWLEDGE_LOOKUP: "router/knowledge_response.jinja2",
    }

    template = template_map.get(intent)
    if not template:
        return ""

    instructions = pm.render(template)
    agent = Agent(
        name=f"Router_{intent.value}",
        model=create_model(),
        instructions=[instructions],
        markdown=True,
    )

    context_str = json.dumps(context, default=str, ensure_ascii=False, indent=2)
    history_str = ""
    if conversation_history:
        for msg in conversation_history[-5:]:
            history_str += f"\n{msg['role']}: {msg['content'][:300]}"

    prompt = f"User: {message}\n\nGraph Context:\n{context_str}"
    if history_str:
        prompt += f"\n\nConversation History:{history_str}"

    response: RunOutput = agent.run(prompt)
    return str(response.content) if response and response.content else ""


def _run_text2sql(
    message: str,
    context: Dict[str, Any],
    graph_tools: GraphSearchTools,
    database: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> RouterResult:
    from src.agents.query_understanding import create_query_understanding_agent, build_parse_prompt
    from src.agents.sql_generator import create_sql_generator_agent, build_generate_sql_prompt
    from src.agents.validation import create_validation_agent, build_validate_prompt

    parse_agent = create_query_understanding_agent()
    parse_prompt = build_parse_prompt(message, conversation_history)
    parse_response = parse_agent.run(parse_prompt, output_schema=ParsedQuery)
    parsed = None
    if parse_response and parse_response.content:
        if isinstance(parse_response.content, ParsedQuery):
            parsed = parse_response.content
        else:
            try:
                parsed = ParsedQuery.model_validate_json(str(parse_response.content))
            except Exception:
                pass
    if not parsed:
        parsed = ParsedQuery(original_text=message)

    schema_ctx = None
    schema_data = context.get("schema", {})
    if schema_data:
        tables = []
        for t in schema_data.get("tables", []):
            from src.core.types import SchemaMatch
            tables.append(SchemaMatch(
                table_name=t.get("name", ""),
                database=t.get("attributes", {}).get("database", database or ""),
                relevance_score=t.get("score", 0.0),
                description=t.get("summary", ""),
            ))
        if tables:
            schema_ctx = SchemaContext(tables=tables)

    sql_agent = create_sql_generator_agent(graph_tools=graph_tools)
    sql_prompt = build_generate_sql_prompt(
        user_query=message,
        schema_context=schema_ctx,
        conversation_history=conversation_history,
    )
    sql_response = sql_agent.run(sql_prompt, output_schema=GeneratedSQL)
    sql_result = None
    if sql_response and sql_response.content:
        if isinstance(sql_response.content, GeneratedSQL):
            sql_result = sql_response.content
        else:
            try:
                sql_result = GeneratedSQL.model_validate_json(str(sql_response.content))
            except Exception:
                pass

    if not sql_result:
        return RouterResult(
            intent=UserIntent.DATA_QUERY,
            response="Failed to generate SQL",
            is_valid=False,
            errors=["SQL generation failed"],
        )

    val_agent = create_validation_agent()
    val_prompt = build_validate_prompt(
        generated_sql=sql_result.sql,
        database=sql_result.database or database or "",
        schema_context=schema_ctx,
        original_query=message,
    )
    val_response = val_agent.run(val_prompt, output_schema=ValidationResult)
    validation = None
    if val_response and val_response.content:
        if isinstance(val_response.content, ValidationResult):
            validation = val_response.content
        else:
            try:
                validation = ValidationResult.model_validate_json(str(val_response.content))
            except Exception:
                pass
    if not validation:
        validation = ValidationResult(is_valid=True)

    if not validation.is_valid and validation.corrected_sql:
        sql_result = GeneratedSQL(
            sql=validation.corrected_sql,
            database=sql_result.database,
            reasoning=sql_result.reasoning + " [auto-corrected]",
            tables_used=sql_result.tables_used,
            has_partition_filter=sql_result.has_partition_filter,
        )

    return RouterResult(
        intent=UserIntent.DATA_QUERY,
        response=sql_result.reasoning,
        sql=sql_result.sql,
        database=sql_result.database or database,
        tables_used=sql_result.tables_used,
        context_used=context,
        is_valid=validation.is_valid,
        errors=validation.errors,
        warnings=validation.warnings,
    )


def route(
    message: str,
    graph_tools: GraphSearchTools,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    database: Optional[str] = None,
    available_databases: Optional[List[str]] = None,
) -> RouterResult:
    intent = classify_intent(message, conversation_history, available_databases)
    logger.info(
        "Intent: %s (%.2f) ambiguous=%s missing=%s entities=%s",
        intent.intent.value, intent.confidence, intent.ambiguous,
        intent.missing_info, intent.entities,
    )

    if intent.database:
        database = intent.database

    if _needs_clarification(intent):
        graph_hints = _gather_graph_hints(intent, message, graph_tools)
        question = _generate_clarification(message, intent, graph_hints, conversation_history)

        suggestions = []
        for h in graph_hints[:5]:
            suggestions.append(h)
        if intent.alternative_intents:
            for alt in intent.alternative_intents:
                suggestions.append(f"Did you mean: {alt}?")

        return RouterResult(
            intent=intent.intent,
            response=question,
            needs_clarification=True,
            clarification_question=question,
            suggestions=suggestions,
            context_used={"graph_hints": graph_hints},
        )

    context: Dict[str, Any] = {}
    if intent.intent in _CONTEXT_INTENTS:
        try:
            context = fetch_graph_context(intent, message, graph_tools)
        except Exception:
            logger.warning("Failed to fetch graph context", exc_info=True)

    if intent.intent == UserIntent.DATA_QUERY:
        return _run_text2sql(message, context, graph_tools, database, conversation_history)

    if intent.intent in (
        UserIntent.SCHEMA_EXPLORATION,
        UserIntent.RELATIONSHIP_DISCOVERY,
        UserIntent.KNOWLEDGE_LOOKUP,
    ):
        response = _respond_with_context(message, intent.intent, context, conversation_history)
        return RouterResult(
            intent=intent.intent,
            response=response,
            context_used=context,
        )

    if intent.intent == UserIntent.FEEDBACK:
        return RouterResult(
            intent=UserIntent.FEEDBACK,
            response="Thank you for the feedback. It has been recorded.",
        )

    if intent.intent == UserIntent.CLARIFICATION:
        graph_hints = _gather_graph_hints(intent, message, graph_tools)
        question = _generate_clarification(message, intent, graph_hints, conversation_history)
        return RouterResult(
            intent=UserIntent.CLARIFICATION,
            response=question,
            needs_clarification=True,
            clarification_question=question,
            suggestions=[h for h in graph_hints[:5]],
        )

    return RouterResult(
        intent=UserIntent.GENERAL,
        response="How can I help you with your data today?",
    )
