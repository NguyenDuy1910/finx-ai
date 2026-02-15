from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_entity_registry, get_search_service, get_memory
from api.models.schemas import (
    BusinessEntityCreate,
    BusinessEntityResponse,
    BusinessEntityUpdate,
    ColumnCreate,
    ColumnResponse,
    ColumnUpdate,
    ContextRequest,
    ContextResponse,
    EdgeResponse,
    EntityMappingCreate,
    EpisodeResponse,
    ForeignKeyCreate,
    JoinCreate,
    QueryPatternCreate,
    QueryPatternResponse,
    RecordFeedbackRequest,
    RecordPatternRequest,
    RecordQueryRequest,
    RecordSchemaRequest,
    SchemaSearchResponse,
    SearchRequest,
    SearchResultItem,
    SuccessResponse,
    TableContextResponse,
    TableCreate,
    TableResponse,
    TableUpdate,
)
from src.knowledge.indexing.entity_indexer import EntityIndexer
from src.knowledge.memory import MemoryManager
from src.knowledge.graph.schemas.edges import (
    EntityMappingEdge,
    ForeignKeyEdge,
    JoinEdge,
)
from src.knowledge.graph.schemas.nodes import (
    BusinessEntityNode,
    ColumnNode,
    QueryPatternNode,
    TableNode,
)
from src.knowledge.retrieval.service import SemanticSearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/tables", response_model=TableResponse, status_code=201)
async def create_table(
    body: TableCreate,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    node = TableNode(**body.model_dump())
    entity = await registry.register_table(node)
    attrs = entity.attributes or {}
    return TableResponse(
        uuid=entity.uuid,
        name=attrs.get("table_name", node.name),
        database=attrs.get("database", node.database),
        description=entity.summary or "",
        partition_keys=attrs.get("partition_keys", []),
        row_count=attrs.get("row_count"),
        storage_format=attrs.get("storage_format", ""),
        location=attrs.get("location", ""),
    )


@router.get("/tables", response_model=List[TableResponse])
async def list_tables(
    database: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    registry: EntityIndexer = Depends(get_entity_registry),
):
    rows = await registry.get_all_tables(database=database, offset=offset, limit=limit)
    results = []
    for row in rows:
        attrs = row.get("attributes", {})
        results.append(TableResponse(
            uuid=row["uuid"],
            name=attrs.get("table_name", row["name"]),
            database=attrs.get("database", ""),
            description=row.get("summary", ""),
            partition_keys=attrs.get("partition_keys", []),
            row_count=attrs.get("row_count"),
            storage_format=attrs.get("storage_format", ""),
            location=attrs.get("location", ""),
        ))
    return results


@router.get("/tables/{table_name}", response_model=TableResponse)
async def get_table(
    table_name: str,
    database: Optional[str] = Query(None),
    registry: EntityIndexer = Depends(get_entity_registry),
):
    row = await registry.get_table(table_name, database)
    if not row:
        raise HTTPException(404, detail=f"Table '{table_name}' not found")
    attrs = row.get("attributes", {})
    return TableResponse(
        uuid=row["uuid"],
        name=attrs.get("table_name", row["name"]),
        database=attrs.get("database", ""),
        description=row.get("summary", ""),
        partition_keys=attrs.get("partition_keys", []),
        row_count=attrs.get("row_count"),
        storage_format=attrs.get("storage_format", ""),
        location=attrs.get("location", ""),
    )


@router.put("/tables/{table_name}", response_model=TableResponse)
async def update_table(
    table_name: str,
    body: TableUpdate,
    database: Optional[str] = Query(None),
    registry: EntityIndexer = Depends(get_entity_registry),
):
    existing = await registry.get_table(table_name, database)
    if not existing:
        raise HTTPException(404, detail=f"Table '{table_name}' not found")
    attrs = existing.get("attributes", {})
    update_data = body.model_dump(exclude_none=True)
    node = TableNode(
        name=attrs.get("table_name", table_name),
        database=attrs.get("database", database or ""),
        description=update_data.get("description", existing.get("summary", "")),
        partition_keys=update_data.get("partition_keys", attrs.get("partition_keys", [])),
        row_count=update_data.get("row_count", attrs.get("row_count")),
        storage_format=update_data.get("storage_format", attrs.get("storage_format", "")),
        location=update_data.get("location", attrs.get("location", "")),
    )
    entity = await registry.register_table(node)
    new_attrs = entity.attributes or {}
    return TableResponse(
        uuid=entity.uuid,
        name=new_attrs.get("table_name", node.name),
        database=new_attrs.get("database", node.database),
        description=entity.summary or "",
        partition_keys=new_attrs.get("partition_keys", []),
        row_count=new_attrs.get("row_count"),
        storage_format=new_attrs.get("storage_format", ""),
        location=new_attrs.get("location", ""),
    )


@router.delete("/tables/{uuid}", response_model=SuccessResponse)
async def delete_table(
    uuid: str,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    await registry.delete_entity(uuid)
    return SuccessResponse(message=f"Deleted table {uuid}")


@router.post("/columns", response_model=ColumnResponse, status_code=201)
async def create_column(
    body: ColumnCreate,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    node = ColumnNode(**body.model_dump())
    entity = await registry.register_column(node)
    attrs = entity.attributes or {}
    return ColumnResponse(
        uuid=entity.uuid,
        name=attrs.get("column_name", node.name),
        table_name=attrs.get("table_name", node.table_name),
        database=attrs.get("database", node.database),
        data_type=attrs.get("data_type", "string"),
        description=entity.summary or "",
        is_primary_key=attrs.get("is_primary_key", False),
        is_foreign_key=attrs.get("is_foreign_key", False),
        is_partition=attrs.get("is_partition", False),
        is_nullable=attrs.get("is_nullable", True),
        sample_values=attrs.get("sample_values", []),
    )


@router.get("/columns", response_model=List[ColumnResponse])
async def get_columns(
    table_name: str = Query(...),
    database: Optional[str] = Query(None),
    registry: EntityIndexer = Depends(get_entity_registry),
):
    rows = await registry.get_columns_for_table(table_name, database)
    results = []
    for r in rows:
        attrs = r.get("attributes", {})
        results.append(ColumnResponse(
            uuid=r["uuid"],
            name=attrs.get("column_name", r["name"]),
            table_name=attrs.get("table_name", table_name),
            database=attrs.get("database", database or ""),
            data_type=attrs.get("data_type", "string"),
            description=r.get("summary", ""),
            is_primary_key=attrs.get("is_primary_key", False),
            is_foreign_key=attrs.get("is_foreign_key", False),
            is_partition=attrs.get("is_partition", False),
            is_nullable=attrs.get("is_nullable", True),
            sample_values=attrs.get("sample_values", []),
        ))
    return results


@router.delete("/columns/{uuid}", response_model=SuccessResponse)
async def delete_column(
    uuid: str,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    await registry.delete_entity(uuid)
    return SuccessResponse(message=f"Deleted column {uuid}")


@router.post("/entities", response_model=BusinessEntityResponse, status_code=201)
async def create_business_entity(
    body: BusinessEntityCreate,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    node = BusinessEntityNode(**body.model_dump())
    entity = await registry.register_business_entity(node)
    attrs = entity.attributes or {}
    return BusinessEntityResponse(
        uuid=entity.uuid,
        name=entity.name,
        domain=attrs.get("domain", "business"),
        description=entity.summary or "",
        synonyms=attrs.get("synonyms", []),
        mapped_tables=attrs.get("mapped_tables", []),
    )


@router.get("/entities", response_model=List[BusinessEntityResponse])
async def list_entities(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    registry: EntityIndexer = Depends(get_entity_registry),
):
    rows = await registry.get_all_entities(offset=offset, limit=limit)
    results = []
    for row in rows:
        attrs = row.get("attributes", {})
        results.append(BusinessEntityResponse(
            uuid=row["uuid"],
            name=row["name"],
            domain=attrs.get("domain", "business"),
            description=row.get("summary", ""),
            synonyms=attrs.get("synonyms", []),
            mapped_tables=attrs.get("mapped_tables", []),
        ))
    return results


@router.get("/entities/resolve", response_model=List[BusinessEntityResponse])
async def resolve_term(
    term: str = Query(...),
    registry: EntityIndexer = Depends(get_entity_registry),
):
    rows = await registry.resolve_term(term)
    return [
        BusinessEntityResponse(
            uuid="",
            name=r.get("entity", ""),
            description=r.get("description", ""),
            synonyms=r.get("synonyms", []),
            mapped_tables=r.get("mapped_tables", []),
        )
        for r in rows
    ]


@router.delete("/entities/{uuid}", response_model=SuccessResponse)
async def delete_business_entity(
    uuid: str,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    await registry.delete_entity(uuid)
    return SuccessResponse(message=f"Deleted entity {uuid}")


@router.post("/patterns", response_model=QueryPatternResponse, status_code=201)
async def create_query_pattern(
    body: QueryPatternCreate,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    node = QueryPatternNode(
        name=body.name,
        intent=body.intent,
        pattern=body.pattern,
        sql_template=body.sql_template,
        tables_involved=body.tables_involved,
        frequency=body.frequency,
    )
    entity = await registry.register_query_pattern(node)
    attrs = entity.attributes or {}
    return QueryPatternResponse(
        uuid=entity.uuid,
        name=entity.name,
        intent=attrs.get("intent", ""),
        pattern=attrs.get("pattern", ""),
        sql_template=attrs.get("sql_template", ""),
        frequency=attrs.get("frequency", 0),
        tables_involved=attrs.get("tables_involved", []),
    )


@router.get("/patterns", response_model=List[QueryPatternResponse])
async def list_patterns(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    registry: EntityIndexer = Depends(get_entity_registry),
):
    rows = await registry.get_all_patterns(offset=offset, limit=limit)
    results = []
    for row in rows:
        attrs = row.get("attributes", {})
        results.append(QueryPatternResponse(
            uuid=row["uuid"],
            name=row["name"],
            intent=attrs.get("intent", ""),
            pattern=attrs.get("pattern", ""),
            sql_template=attrs.get("sql_template", ""),
            frequency=attrs.get("frequency", 0),
            tables_involved=attrs.get("tables_involved", []),
        ))
    return results


@router.delete("/patterns/{uuid}", response_model=SuccessResponse)
async def delete_query_pattern(
    uuid: str,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    await registry.delete_entity(uuid)
    return SuccessResponse(message=f"Deleted pattern {uuid}")


@router.post("/joins", response_model=SuccessResponse, status_code=201)
async def create_join(
    body: JoinCreate,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    src_table = await registry.get_table(body.source_table, body.database)
    tgt_table = await registry.get_table(body.target_table, body.database)
    if not src_table:
        raise HTTPException(404, detail=f"Source table '{body.source_table}' not found")
    if not tgt_table:
        raise HTTPException(404, detail=f"Target table '{body.target_table}' not found")
    edge = JoinEdge(**body.model_dump())
    await registry.register_join(edge, src_table["uuid"], tgt_table["uuid"])
    return SuccessResponse(message=f"Join created: {body.source_table} -> {body.target_table}")


@router.post("/foreign-keys", response_model=SuccessResponse, status_code=201)
async def create_foreign_key(
    body: ForeignKeyCreate,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    src_table = await registry.get_table(body.source_table, body.database)
    tgt_table = await registry.get_table(body.target_table, body.database)
    if not src_table:
        raise HTTPException(404, detail=f"Source table '{body.source_table}' not found")
    if not tgt_table:
        raise HTTPException(404, detail=f"Target table '{body.target_table}' not found")
    edge = ForeignKeyEdge(**body.model_dump())
    await registry.register_foreign_key(edge, src_table["uuid"], tgt_table["uuid"])
    return SuccessResponse(
        message=f"FK created: {body.source_table}.{body.source_column} -> {body.target_table}.{body.target_column}",
    )


@router.post("/entity-mappings", response_model=SuccessResponse, status_code=201)
async def create_entity_mapping(
    body: EntityMappingCreate,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    entities = await registry.resolve_term(body.entity_name)
    if not entities:
        raise HTTPException(404, detail=f"Entity '{body.entity_name}' not found")
    table = await registry.get_table(body.table_name, body.database)
    if not table:
        raise HTTPException(404, detail=f"Table '{body.table_name}' not found")
    entity_records = await registry._execute(
        """
        MATCH (e:BusinessEntity)
        WHERE toLower(e.name) = toLower($name)
        RETURN e.uuid AS uuid
        LIMIT 1
        """,
        name=body.entity_name,
    )
    if not entity_records:
        raise HTTPException(404, detail=f"Entity '{body.entity_name}' not found in graph")
    edge = EntityMappingEdge(**body.model_dump())
    await registry.register_entity_mapping(edge, entity_records[0]["uuid"], table["uuid"])
    return SuccessResponse(message=f"Mapping created: {body.entity_name} -> {body.table_name}")


@router.get("/edges/{table_name}", response_model=List[EdgeResponse])
async def get_edges_for_table(
    table_name: str,
    registry: EntityIndexer = Depends(get_entity_registry),
):
    rows = await registry.search_entity_edges(table_name)
    return [EdgeResponse(**r) for r in rows]


@router.get("/related/{table_name}", response_model=List[dict])
async def get_related_tables(
    table_name: str,
    database: Optional[str] = Query(None),
    registry: EntityIndexer = Depends(get_entity_registry),
):
    return await registry.find_related_tables(table_name, database)


@router.post("/search/schema", response_model=SchemaSearchResponse)
async def search_schema(
    body: SearchRequest,
    search: SemanticSearchService = Depends(get_search_service),
):
    result = await search.search_schema(
        query=body.query,
        database=body.database,
        top_k=body.top_k,
        threshold=body.threshold,
    )
    return SchemaSearchResponse(
        tables=[SearchResultItem(**r.to_dict()) for r in result.tables],
        columns=[SearchResultItem(**r.to_dict()) for r in result.columns],
        entities=[SearchResultItem(**r.to_dict()) for r in result.entities],
        patterns=result.patterns,
        context=[TableContextResponse(**c) for c in result.context],
        ranked_results=result.ranked_results,
        query_analysis=result.query_analysis,
        search_metadata=result.search_metadata,
    )


@router.get("/search/tables", response_model=list[SearchResultItem])
async def search_tables(
    q: str = Query(...),
    database: Optional[str] = Query(None),
    top_k: int = Query(5, ge=1, le=50),
    search: SemanticSearchService = Depends(get_search_service),
):
    results = await search.search_tables(q, top_k=top_k, database=database)
    return [SearchResultItem(**r.to_dict()) for r in results]


@router.get("/search/columns", response_model=list[SearchResultItem])
async def search_columns(
    q: str = Query(...),
    database: Optional[str] = Query(None),
    top_k: int = Query(5, ge=1, le=50),
    search: SemanticSearchService = Depends(get_search_service),
):
    results = await search.search_columns(q, top_k=top_k, database=database)
    return [SearchResultItem(**r.to_dict()) for r in results]


@router.get("/search/entities", response_model=list[SearchResultItem])
async def search_entities(
    q: str = Query(...),
    top_k: int = Query(5, ge=1, le=50),
    search: SemanticSearchService = Depends(get_search_service),
):
    results = await search.search_entities(q, top_k=top_k)
    return [SearchResultItem(**r.to_dict()) for r in results]


@router.post("/memory/schema", response_model=EpisodeResponse, status_code=201)
async def record_schema(
    body: RecordSchemaRequest,
    memory: MemoryManager = Depends(get_memory),
):
    episode_id = await memory.record_schema(**body.model_dump())
    return EpisodeResponse(episode_id=episode_id)


@router.post("/memory/query", response_model=EpisodeResponse, status_code=201)
async def record_query(
    body: RecordQueryRequest,
    memory: MemoryManager = Depends(get_memory),
):
    episode_id = await memory.record_query(**body.model_dump())
    return EpisodeResponse(episode_id=episode_id)


@router.post("/memory/feedback", response_model=EpisodeResponse, status_code=201)
async def record_feedback(
    body: RecordFeedbackRequest,
    memory: MemoryManager = Depends(get_memory),
):
    episode_id = await memory.record_feedback(**body.model_dump())
    return EpisodeResponse(episode_id=episode_id)


@router.post("/memory/pattern", response_model=EpisodeResponse, status_code=201)
async def record_pattern(
    body: RecordPatternRequest,
    memory: MemoryManager = Depends(get_memory),
):
    episode_id = await memory.record_pattern(**body.model_dump())
    return EpisodeResponse(episode_id=episode_id)


@router.post("/memory/context", response_model=ContextResponse)
async def get_context(
    body: ContextRequest,
    memory: MemoryManager = Depends(get_memory),
):
    ctx = await memory.get_context(
        query=body.query,
        database=body.database,
        top_k=body.top_k,
    )
    return ContextResponse(**ctx)
