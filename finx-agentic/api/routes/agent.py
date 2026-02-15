from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_client, get_memory, get_pg_db
from api.models.schemas import ChatRequest, ChatResponse, Text2SQLRequest, Text2SQLResponse
from src.core.agentops_tracker import start_trace, end_trace, update_trace_metadata
from src.knowledge.client import GraphitiClient
from src.knowledge.memory import MemoryManager
from src.tools.graph_tools import GraphSearchTools
from src.workflows.text2sql import Text2SQLWorkflow
from src.core.intent import RouterResult
from src.core.types import Text2SQLResult
from src.agents.intent_router import route as route_intent

from agno.db.postgres import PostgresDb

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/text2sql", response_model=Text2SQLResponse)
async def text2sql(
    body: Text2SQLRequest,
    client: GraphitiClient = Depends(get_client),
    memory: MemoryManager = Depends(get_memory),
    pg_db: PostgresDb = Depends(get_pg_db),
):
    trace = start_trace(name="text2sql-api", tags=["api", "text2sql"])
    try:
        update_trace_metadata({
            "endpoint": "/api/v1/agent/text2sql",
            "query": body.query[:200],
            "database": body.database or "",
        })
        graph_tools = GraphSearchTools(
            client=client,
            default_database=body.database,
        )
        workflow = Text2SQLWorkflow(
            database=body.database or "",
            graph_tools=graph_tools,
            db=pg_db,
        )
        output = workflow.run(body.query)
        result = Text2SQLResult.model_validate_json(output.content)

        episode_id: Optional[str] = None
        try:
            episode_id = await memory.record_query(
                natural_language=body.query,
                generated_sql=result.sql.sql,
                tables_used=result.sql.tables_used,
                database=result.sql.database or body.database or "",
                intent=result.parsed.intent.value,
                success=result.validation.is_valid,
            )
        except Exception:
            logger.warning("Failed to record query episode", exc_info=True)

        return Text2SQLResponse(
            query=body.query,
            sql=result.sql.sql,
            database=result.sql.database,
            tables_used=result.sql.tables_used,
            reasoning=result.sql.reasoning,
            is_valid=result.validation.is_valid,
            errors=result.validation.errors,
            warnings=result.validation.warnings,
            episode_id=episode_id,
        )
    except Exception as e:
        logger.exception("Text2SQL workflow failed")
        end_trace(trace, end_state="Fail", error_message=str(e))
        raise HTTPException(500, detail=str(e))
    else:
        end_trace(trace, end_state="Success")


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    client: GraphitiClient = Depends(get_client),
    memory: MemoryManager = Depends(get_memory),
    pg_db: PostgresDb = Depends(get_pg_db),
):
    trace = start_trace(name="chat-api", tags=["api", "chat"])
    try:
        update_trace_metadata({
            "endpoint": "/api/v1/agent/chat",
            "message": body.message[:200],
            "database": body.database or "",
        })
        graph_tools = GraphSearchTools(
            client=client,
            default_database=body.database,
        )
        result: RouterResult = route_intent(
            message=body.message,
            graph_tools=graph_tools,
            conversation_history=body.conversation_history,
            database=body.database,
            available_databases=body.available_databases,
            db=pg_db,
        )

        episode_id: Optional[str] = None
        if result.sql:
            try:
                episode_id = await memory.record_query(
                    natural_language=body.message,
                    generated_sql=result.sql,
                    tables_used=result.tables_used,
                    database=result.database or body.database or "",
                    intent=result.intent.value,
                    success=result.is_valid,
                )
            except Exception:
                logger.warning("Failed to record query episode", exc_info=True)

        return ChatResponse(
            intent=result.intent.value,
            response=result.response,
            sql=result.sql,
            database=result.database,
            tables_used=result.tables_used,
            context_used=result.context_used,
            episode_id=episode_id,
            is_valid=result.is_valid,
            errors=result.errors,
            warnings=result.warnings,
            needs_clarification=result.needs_clarification,
            clarification_question=result.clarification_question,
            suggestions=result.suggestions,
        )
    except Exception as e:
        logger.exception("Chat routing failed")
        end_trace(trace, end_state="Fail", error_message=str(e))
        raise HTTPException(500, detail=str(e))
    else:
        end_trace(trace, end_state="Success")
