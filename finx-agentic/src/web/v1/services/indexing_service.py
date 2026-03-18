from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.graph.client import GraphitiClient
from src.knowledge.indexing.schema_metadata import SchemaMetadataWorkflow
from src.knowledge.indexing.document_ingestion import (
    DocumentIngestionWorkflow,
    IngestionRequest,
    IngestionInputType,
)
from src.agents.schema_enricher import SourceType

logger = logging.getLogger(__name__)


class IndexingService:

    def __init__(self, client: GraphitiClient) -> None:
        self._client = client
        self._doc_workflow = DocumentIngestionWorkflow(graph=client)

    async def index_schemas(
        self,
        schema_path: str,
        database: Optional[str] = None,
        skip_existing: bool = False,
    ) -> Dict[str, Any]:
        logger.info(
            "index_schemas called (schema_path=%s, database=%s, skip_existing=%s)",
            schema_path, database, skip_existing,
        )
        pipeline = SchemaMetadataWorkflow(graph=self._client)
        items = self._load_items(schema_path=schema_path, database=database)

        skipped = 0
        if skip_existing:
            indexed_tables = await pipeline.get_indexed_tables()
            filtered_items: list[dict[str, Any]] = []
            for item in items:
                full_name = self._full_table_name(
                    str(item.get("name", "")),
                    str(item.get("database", "")),
                )
                if full_name in indexed_tables:
                    skipped += 1
                    continue
                filtered_items.append(item)
            items = filtered_items

        if not items:
            return {
                "tables": 0,
                "columns": 0,
                "entities": 0,
                "edges": 0,
                "domains": 0,
                "skipped": skipped,
            }

        result = await pipeline.index_items(items)
        step_results = result.get("step_results", [])

        tables = sum(step.get("items_processed", 0) for step in step_results)
        graph_stats = self._extract_graph_stats(step_results)
        domains = len({
            str(item.get("domain", "")).strip()
            for item in items
            if str(item.get("domain", "")).strip()
        })

        return {
            "tables": tables,
            "columns": sum(
                len(item.get("columns", []))
                for item in items
                if isinstance(item.get("columns"), list)
            ),
            "entities": graph_stats.get("nodes", 0),
            "edges": graph_stats.get("edges", 0),
            "domains": domains,
            "skipped": skipped,
        }

    async def initialize_graph(self) -> None:
        await self._client.initialize()
        logger.info("Graph initialized via IndexingService")

    async def get_stats(self) -> Dict[str, Any]:
        try:
            result = await self._client.execute_query(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"
            )
            entities: Dict[str, int] = {}
            for row in result:
                if isinstance(row, dict):
                    entities[str(row.get("label", ""))] = int(row.get("cnt", 0))
                elif isinstance(row, (list, tuple)) and len(row) >= 2:
                    entities[str(row[0])] = int(row[1])
            return {"entities": entities, "episodes": {}}
        except Exception as e:
            logger.error("Failed to get graph stats: %s", e)
            return {"entities": {}, "episodes": {}}

    async def record_feedback(
        self,
        natural_language: str,
        generated_sql: str,
        feedback: str,
        rating: Optional[int] = None,
        corrected_sql: str = "",
    ) -> str:
        """Write analyst feedback as a text episode to the knowledge graph."""
        import json as _json
        body = {
            "natural_language": natural_language,
            "generated_sql": generated_sql,
            "feedback": feedback,
            "rating": rating,
            "corrected_sql": corrected_sql,
        }
        try:
            result = await self._client.write_episode(
                name="analyst_feedback",
                body=_json.dumps(body),
                saga="feedback",
                source_description="Analyst feedback on generated SQL",
            )
            return str(result)
        except Exception as e:
            logger.error("Failed to store feedback: %s", e)
            return "error"

    async def ingest_files(
        self,
        files: List[tuple[bytes, str, str]],
        entity_name: str = "",
        tags: Optional[List[str]] = None,
        write_to_graph: bool = True,
    ) -> Dict[str, Any]:
        tag_list = tags or []
        requests: list[IngestionRequest] = []
        for raw_bytes, filename, content_type in files:
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            source_type = SourceType.PDF if ext == "pdf" else SourceType.TEXT
            requests.append(IngestionRequest(
                input_type=IngestionInputType.FILE_BYTES,
                source_type=source_type,
                source_name=filename,
                content_bytes=raw_bytes,
                filename=filename,
                content_type=content_type,
                entity_name=entity_name,
                tags=tag_list,
            ))
        if not requests:
            return {"status": "error", "summary": {"errors": ["No files provided"]}}
        result = await self._doc_workflow.run(requests, write_to_graph=write_to_graph)
        return result

    async def ingest_url(
        self,
        url: str,
        entity_name: str = "",
        tags: Optional[List[str]] = None,
        confluence_base_url: Optional[str] = None,
        confluence_username: Optional[str] = None,
        confluence_api_token: Optional[str] = None,
        write_to_graph: bool = True,
    ) -> Dict[str, Any]:
        result = await self._doc_workflow.ingest_url(
            url,
            entity_name=entity_name,
            tags=tags or [],
            confluence_base_url=confluence_base_url,
            confluence_username=confluence_username,
            confluence_api_token=confluence_api_token,
            write_to_graph=write_to_graph,
        )
        return result

    async def ingest_text(
        self,
        text: str,
        source_name: str = "",
        entity_name: str = "",
        tags: Optional[List[str]] = None,
        write_to_graph: bool = True,
    ) -> Dict[str, Any]:
        result = await self._doc_workflow.ingest_text(
            text,
            source_name=source_name,
            entity_name=entity_name,
            tags=tags or [],
            write_to_graph=write_to_graph,
        )
        return result

    def _load_items(
        self,
        *,
        schema_path: str,
        database: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        path = Path(schema_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Schema file not found: {path}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_items = self._extract_items(payload)
        normalized_items: list[dict[str, Any]] = [
            self._override_database(item, database)
            for item in raw_items
            if isinstance(item, dict)
        ]
        return normalized_items

    @staticmethod
    def _extract_items(payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("items", "tables", "schemas"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        raise ValueError("Index payload must be a list or contain an items/tables/schemas list")

    @staticmethod
    def _override_database(item: Any, database: Optional[str]) -> Any:
        if not database or not isinstance(item, dict):
            return item
        patched = dict(item)
        patched["database"] = database
        return patched

    @staticmethod
    def _extract_graph_stats(step_results: list[dict[str, Any]]) -> dict[str, int]:
        graph_stats: dict[str, int] = {}
        for step in step_results:
            details = step.get("details", {})
            for key in ("nodes", "edges"):
                if key in details:
                    graph_stats[key] = details.get(key, 0)
        return graph_stats

    @staticmethod
    def _full_table_name(table_name: str, database: str) -> str:
        if "." in table_name:
            return table_name
        return f"{database}.{table_name}" if database else table_name
