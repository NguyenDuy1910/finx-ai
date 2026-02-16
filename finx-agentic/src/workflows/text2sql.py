import asyncio
import logging
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Union

from agno.agent import RunOutput
from agno.db.base import BaseDb
from agno.workflow import Workflow

from src.agents.query_understanding import create_query_understanding_agent, build_parse_prompt
from src.agents.schema_discovery import create_schema_discovery_agent, build_discover_prompt
from src.agents.sql_generator import create_sql_generator_agent, build_generate_sql_prompt
from src.agents.validation import create_validation_agent, build_validate_prompt
from src.agents.learning import create_learning_agent, build_store_episode_prompt
from src.core.agentops_tracker import operation, update_trace_metadata
from src.core.cost_tracker import CostTracker
from src.core.types import (
    ParsedQuery,
    SchemaContext,
    GeneratedSQL,
    ValidationResult,
    Text2SQLResult,
)
from src.tools.graph_tools import GraphSearchTools

logger = logging.getLogger(__name__)


class Text2SQLWorkflow(Workflow):

    def __init__(
        self,
        database: str = "",
        graph_tools: Optional[GraphSearchTools] = None,
        max_retries: int = 2,
        track_cost: bool = True,
        db: Optional[BaseDb] = None,
        **kwargs,
    ):
        super().__init__(
            name=kwargs.pop("name", "text2sql"),
            description=kwargs.pop("description", "End-to-end natural language to SQL workflow"),
            db=db,
            **kwargs,
        )
        self.database = database
        self.graph_tools = graph_tools
        self.max_retries = max_retries
        self.track_cost = track_cost
        self.cost_tracker: Optional[CostTracker] = None

    def _build_step_state(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = dict(self.session_state or {})
        if extra:
            state.update(extra)
        return state

    async def arun(
        self,
        input: Union[str, List, Dict, Any],
        *,
        stream: Optional[bool] = None,
        **kwargs,
    ) -> Union[RunOutput, AsyncIterator]:
        user_query = input if isinstance(input, str) else str(input)
        session_state = self.session_state or {}
        conversation_history = session_state.get("conversation_history", [])

        tracker = CostTracker() if self.track_cost else None
        self.cost_tracker = tracker

        update_trace_metadata({
            "workflow": "text2sql",
            "database": self.database,
            "query": user_query[:200],
        })

        parsed = await self._step_parse(user_query, conversation_history, tracker)
        if parsed is None:
            return RunOutput(content="Failed to parse query")

        schema_ctx = await self._step_discover(parsed, tracker)

        step_context = {}
        if schema_ctx:
            step_context["schema_context"] = schema_ctx.model_dump_json(indent=2)

        sql_result = await self._step_generate(user_query, schema_ctx, conversation_history, tracker, step_context)
        if sql_result is None:
            return RunOutput(content="Failed to generate SQL")

        validation = await self._step_validate(sql_result, schema_ctx, user_query, tracker)

        if validation and not validation.is_valid and validation.corrected_sql:
            sql_result = GeneratedSQL(
                sql=validation.corrected_sql,
                database=sql_result.database,
                reasoning=sql_result.reasoning + " [auto-corrected]",
                tables_used=sql_result.tables_used,
                has_partition_filter=sql_result.has_partition_filter,
            )

        await self._step_learn(user_query, sql_result, parsed, tracker)

        result = Text2SQLResult(
            query=user_query,
            parsed=parsed,
            schema_context=schema_ctx or SchemaContext(),
            sql=sql_result,
            validation=validation or ValidationResult(is_valid=True),
        )

        self.update_session_state(
            conversation_history=conversation_history + [
                {"role": "user", "content": user_query},
                {"role": "assistant", "content": sql_result.sql},
            ],
            last_parsed=parsed.model_dump(),
            last_sql=sql_result.sql,
            last_tables=sql_result.tables_used,
        )

        if tracker:
            tracker.print_summary()

        return RunOutput(content=result.model_dump_json(indent=2))

    def run(
        self,
        input: Union[str, List, Dict, Any],
        *,
        stream: Optional[bool] = None,
        **kwargs,
    ) -> Union[RunOutput, Iterator]:
        """Sync wrapper – delegates to arun()."""
        return asyncio.run(self.arun(input, stream=stream, **kwargs))

    @operation(name="text2sql_parse_query")
    async def _step_parse(
        self,
        user_query: str,
        conversation_history: List[Dict[str, str]],
        tracker: Optional[CostTracker] = None,
    ) -> Optional[ParsedQuery]:
        agent = create_query_understanding_agent(
            session_id=self.session_id,
            session_state=self._build_step_state(),
        )
        prompt = build_parse_prompt(
            user_query=user_query,
            conversation_history=conversation_history,
        )
        response: RunOutput = await agent.arun(prompt, output_schema=ParsedQuery)
        if tracker:
            tracker.track(response, step="query_understanding")
        if response and response.content:
            if isinstance(response.content, ParsedQuery):
                return response.content
            try:
                return ParsedQuery.model_validate_json(str(response.content))
            except Exception:
                logger.warning("Failed to parse query understanding response")
                return ParsedQuery(original_text=user_query)
        return ParsedQuery(original_text=user_query)

    @operation(name="text2sql_discover_schema")
    async def _step_discover(
        self,
        parsed: ParsedQuery,
        tracker: Optional[CostTracker] = None,
    ) -> Optional[SchemaContext]:
        if not self.graph_tools:
            return None
        agent = create_schema_discovery_agent(
            graph_tools=self.graph_tools,
            session_id=self.session_id,
            session_state=self._build_step_state(),
        )
        prompt = build_discover_prompt(parsed_query=parsed, database=self.database)
        response: RunOutput = await agent.arun(prompt, output_schema=SchemaContext)
        if tracker:
            tracker.track(response, step="schema_discovery")
        if response and response.content:
            if isinstance(response.content, SchemaContext):
                return response.content
            try:
                return SchemaContext.model_validate_json(str(response.content))
            except Exception:
                logger.warning("Failed to parse schema discovery response")
        return None

    @operation(name="text2sql_generate_sql")
    async def _step_generate(
        self,
        user_query: str,
        schema_ctx: Optional[SchemaContext],
        conversation_history: List[Dict[str, str]],
        tracker: Optional[CostTracker] = None,
        step_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[GeneratedSQL]:
        agent = create_sql_generator_agent(
            graph_tools=self.graph_tools,
            session_id=self.session_id,
            session_state=self._build_step_state(step_context),
        )
        prompt = build_generate_sql_prompt(
            user_query=user_query,
            schema_context=schema_ctx,
            conversation_history=conversation_history,
        )
        response: RunOutput = await agent.arun(prompt, output_schema=GeneratedSQL)
        if tracker:
            tracker.track(response, step="sql_generation")
        if response and response.content:
            if isinstance(response.content, GeneratedSQL):
                return response.content
            try:
                return GeneratedSQL.model_validate_json(str(response.content))
            except Exception:
                logger.warning("Failed to parse SQL generation response")
        return None

    @operation(name="text2sql_validate_sql")
    async def _step_validate(
        self,
        sql_result: GeneratedSQL,
        schema_ctx: Optional[SchemaContext],
        original_query: str,
        tracker: Optional[CostTracker] = None,
    ) -> Optional[ValidationResult]:
        agent = create_validation_agent(
            session_id=self.session_id,
            session_state=self._build_step_state(),
        )
        prompt = build_validate_prompt(
            generated_sql=sql_result.sql,
            database=sql_result.database or self.database,
            schema_context=schema_ctx,
            original_query=original_query,
        )
        response: RunOutput = await agent.arun(prompt, output_schema=ValidationResult)
        if tracker:
            tracker.track(response, step="validation")
        if response and response.content:
            if isinstance(response.content, ValidationResult):
                return response.content
            try:
                return ValidationResult.model_validate_json(str(response.content))
            except Exception:
                logger.warning("Failed to parse validation response")
        return None

    @operation(name="text2sql_learn")
    async def _step_learn(
        self,
        user_query: str,
        sql_result: GeneratedSQL,
        parsed: ParsedQuery,
        tracker: Optional[CostTracker] = None,
    ) -> None:
        if not self.graph_tools:
            return
        try:
            agent = create_learning_agent(
                graph_tools=self.graph_tools,
                session_id=self.session_id,
                session_state=self._build_step_state({
                    "last_sql": sql_result.sql,
                    "last_tables": sql_result.tables_used,
                }),
            )
            prompt = build_store_episode_prompt(
                natural_language=user_query,
                generated_sql=sql_result.sql,
                tables_used=sql_result.tables_used,
                database=sql_result.database or self.database,
                intent=parsed.intent.value,
                success=True,
            )
            response = await agent.arun(prompt)
            if tracker:
                tracker.track(response, step="learning")
        except Exception as e:
            logger.warning("Learning step failed: %s", e)

