from __future__ import annotations

import logging
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from src.web.v1.deps import AppState, get_app_state
from src.web.v1.schemas.indexing import (
    IndexRequest,
    IndexResponse,
    PreviewRequest,
    PreviewResponse,
    PreviewColumnDesign,
    PreviewRelationship,
    KGNode,
    KGEdge,
    LLMCost,
    ProgressResponse,
    StatsResponse,
    IndexedTablesResponse,
    UploadContextResponse,
    FetchUrlRequest,
    FetchUrlResponse,
    IngestFilesResponse,
    IngestUrlRequest,
    IngestUrlResponse,
    IngestTextRequest,
    IngestTextResponse,
)
from src.knowledge.indexing.schema_metadata import SchemaMetadataWorkflow
from src.knowledge.indexing.document_ingestion import DocumentIngestionWorkflow
from src.agents.schema_enricher import KnowledgeSource, SchemaEnricher, SourceType
from src.knowledge.indexing.utils.doc_parser import extract_text, fetch_url_content, _is_confluence_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/indexing", tags=["indexing"])

_cache: dict = {}


def _get_indexing_workflow(state: AppState = Depends(get_app_state)) -> SchemaMetadataWorkflow:
    if "indexing_workflow" not in _cache:
        _cache["indexing_workflow"] = SchemaMetadataWorkflow(graph=state.client)
    return _cache["indexing_workflow"]


def _get_enricher() -> SchemaEnricher:
    if "schema_enricher" not in _cache:
        _cache["schema_enricher"] = SchemaEnricher()
    return _cache["schema_enricher"]


# ── Existing endpoints ──────────────────────────────────────────────────────

@router.post("/run", response_model=IndexResponse)
async def run_indexing(
    body: IndexRequest,
    pipeline: SchemaMetadataWorkflow = Depends(_get_indexing_workflow),
):
    # Prefer source-agnostic payload ("items"), keep legacy "tables" input.
    if body.items:
        items = [item.model_dump() for item in body.items]
    else:
        items = [
            {"name": table.get("name", ""), **table}
            for table in body.tables
            if isinstance(table, dict)
        ]
    raw = await pipeline.index_items(items=items)
    step_results = raw.get("step_results", [])

    tables_indexed = 0
    tables_failed = 0
    graph_stats: dict = {}
    all_errors: list[str] = []
    llm_cost_data: dict = {}

    for sr in step_results:
        tables_indexed += sr.get("items_processed", 0)
        tables_failed += sr.get("items_failed", 0)
        details = sr.get("details", {})
        if details.get("nodes"):
            graph_stats["nodes"] = details.get("nodes", 0)
            graph_stats["edges"] = details.get("edges", 0)
            llm_cost_data = details.get("llm_cost", {})
        all_errors.extend(sr.get("errors", []))

    return IndexResponse(
        status=raw.get("status", "success"),
        tables_indexed=tables_indexed,
        tables_failed=tables_failed,
        graph_stats=graph_stats,
        errors=all_errors,
        llm_cost=LLMCost(
            input_tokens=llm_cost_data.get("input_tokens", 0),
            output_tokens=llm_cost_data.get("output_tokens", 0),
            embedding_tokens=llm_cost_data.get("embedding_tokens", 0),
            llm_calls=llm_cost_data.get("llm_calls", 0),
            embedding_calls=llm_cost_data.get("embedding_calls", 0),
            cost_usd=llm_cost_data.get("cost_usd", 0.0),
            duration_s=0.0,
            breakdown=llm_cost_data.get("breakdown", {}),
        ),
    )


@router.get("/progress", response_model=ProgressResponse)
async def get_progress():
    return ProgressResponse(status="idle")


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    pipeline: SchemaMetadataWorkflow = Depends(_get_indexing_workflow),
):
    stats = await pipeline.get_stats()
    return StatsResponse(**stats)


@router.get("/indexed-tables", response_model=IndexedTablesResponse)
async def get_indexed_tables(
    pipeline: SchemaMetadataWorkflow = Depends(_get_indexing_workflow),
):
    names = await pipeline.get_indexed_tables()
    table_list = sorted(names)
    return IndexedTablesResponse(tables=table_list, count=len(table_list))


# ── New: Preview endpoint ───────────────────────────────────────────────────

@router.post("/preview", response_model=PreviewResponse)
async def preview_table(
    body: PreviewRequest,
    enricher: SchemaEnricher = Depends(_get_enricher),
):
    """Run the SchemaEnricher on a single table (dry-run — nothing is persisted).

    Accepts:
    * ``knowledge_sources`` — structured list of typed documents (pdf_extract,
      confluence_page, url_content, raw_text, table_schema). **Preferred.**
    * ``context_text`` — legacy plain-text string (treated as raw_text).
    """
    # Build typed KnowledgeSource list from structured sources
    sources: list[KnowledgeSource] = []
    for ks in body.knowledge_sources:
        try:
            stype = SourceType(ks.source_type)
        except ValueError:
            stype = SourceType.TEXT
        if ks.content.strip():
            sources.append(KnowledgeSource(
                source_type=stype,
                source_name=ks.source_name,
                content=ks.content,
            ))

    # Legacy plain-text fallback
    legacy_docs = [body.context_text] if body.context_text.strip() else []

    t0 = time.perf_counter()
    try:
        enriched = await enricher.enrich_table(
            schema=body.table_schema,
            context_tables=body.context_tables,
            context_documents=legacy_docs if not sources else None,
            knowledge_sources=sources if sources else None,
        )
    except Exception as exc:
        logger.error("Preview failed for table %s: %s", body.table_schema.name, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    elapsed = time.perf_counter() - t0

    # Map enriched columns
    enriched_cols = [
        PreviewColumnDesign(
            name=col.name,
            data_type=col.data_type,
            description=col.description,
            ai_description=col.ai_description,
            business_terms=col.business_terms,
            is_primary_key=col.is_primary_key,
            is_foreign_key=bool(col.column_type and col.column_type.lower() == "foreign_key"),
            column_type=col.column_type,
            foreign_key_ref="",
        )
        for col in enriched.enriched_columns
    ]

    # Map relationships
    rels = [
        PreviewRelationship(
            source_table=rel.source_table,
            target_table=rel.target_table,
            relationship_type=rel.relationship_type,
            source_column=rel.source_column,
            target_column=rel.target_column,
            description=rel.description,
        )
        for rel in enriched.relationships
    ]

    # Map KG nodes / edges — validate / coerce
    kg_nodes = [
        KGNode(
            id=n.get("id", f"node-{i}"),
            label=n.get("label", ""),
            type=n.get("type", "table"),
            description=n.get("description", ""),
        )
        for i, n in enumerate(enriched.kg_nodes)
        if isinstance(n, dict)
    ]
    kg_edges = [
        KGEdge(
            source=e.get("source", ""),
            target=e.get("target", ""),
            label=e.get("label", ""),
            type=e.get("type", "structural"),
        )
        for e in enriched.kg_edges
        if isinstance(e, dict) and e.get("source") and e.get("target")
    ]

    return PreviewResponse(
        name=enriched.name,
        database=enriched.database,
        description=enriched.description,
        ai_description=enriched.ai_description,
        entity_name=enriched.entity_name,
        domain=enriched.domain,
        synonyms=enriched.synonyms,
        tags=enriched.tags,
        enriched_columns=enriched_cols,
        relationships=rels,
        kg_nodes=kg_nodes,
        kg_edges=kg_edges,
        llm_cost=LLMCost(duration_s=round(elapsed, 3)),
    )


# ── New: Upload-context endpoint ─────────────────────────────────────────────

@router.post("/upload-context", response_model=UploadContextResponse)
async def upload_context_document(
    file: UploadFile = File(...),
):
    """Upload a document (PDF, CSV, Excel, TXT) and extract plain text from it.

    The extracted text can then be passed as ``context_text`` in the /preview
    request to inject business documentation into the enrichment prompt.
    """
    raw_bytes = await file.read()
    filename = file.filename or "document"
    content_type = file.content_type or ""

    try:
        text = extract_text(raw_bytes, filename=filename, content_type=content_type)
    except ImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to extract text from %s: %s", filename, exc)
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse file '{filename}': {exc}",
        ) from exc

    # Cap text length to avoid overloading prompts (128k chars ≈ ~32k tokens)
    max_chars = 128_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated for prompt size]"
        logger.warning("Context document %s truncated to %d chars", filename, max_chars)

    return UploadContextResponse(
        text=text,
        char_count=len(text),
        source_name=filename,
    )


MAX_CONTEXT_CHARS = 128_000


@router.post("/fetch-url", response_model=FetchUrlResponse)
async def fetch_url_context(body: FetchUrlRequest):
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    is_confluence = _is_confluence_url(url)

    try:
        result = fetch_url_content(
            url,
            confluence_base_url=body.confluence_base_url,
            confluence_username=body.confluence_username,
            confluence_api_token=body.confluence_api_token,
        )
    except ImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to fetch URL %s: %s", url, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch content from URL: {exc}",
        ) from exc

    # ConfluenceContent carries both text and html; plain str has only text
    from src.knowledge.indexing.utils.doc_parser import ConfluenceContent

    if isinstance(result, ConfluenceContent):
        text = result.text
        raw_html = result.html
    else:
        text = result
        raw_html = ""

    if len(text) > MAX_CONTEXT_CHARS:
        text = text[:MAX_CONTEXT_CHARS] + "\n... [truncated for prompt size]"
        logger.warning("URL content from %s truncated to %d chars", url, MAX_CONTEXT_CHARS)

    source_name = url.split("/")[-1] or url[:60]

    return FetchUrlResponse(
        text=text,
        html=raw_html,
        char_count=len(text),
        source_name=source_name,
        is_confluence=is_confluence,
    )


def _get_ingestion_workflow(state: AppState = Depends(get_app_state)) -> DocumentIngestionWorkflow:
    if "document_ingestion_workflow" not in _cache:
        _cache["document_ingestion_workflow"] = DocumentIngestionWorkflow(graph=state.client)
    return _cache["document_ingestion_workflow"]


@router.post("/ingest/files", response_model=IngestFilesResponse)
async def ingest_files(
    files: List[UploadFile] = File(...),
    entity_name: str = Form(default=""),
    tags: str = Form(default=""),
    write_to_graph: bool = Form(default=True),
    workflow: DocumentIngestionWorkflow = Depends(_get_ingestion_workflow),
):
    """Ingest one or more uploaded files (PDF, TXT, CSV, XLSX) into the knowledge graph.

    Each file is parsed, chunked with the strategy appropriate for its type,
    and written as fine-grained graph episodes.

    Form fields:
        entity_name: Optional table / entity name to associate with all files.
        tags: Comma-separated tag list (e.g. "finance,pii").
        write_to_graph: Set to false to parse and chunk only (no graph write).
    """
    from src.knowledge.indexing.document_ingestion import IngestionRequest, IngestionInputType
    from src.agents.schema_enricher import SourceType

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    requests = []
    for upload in files:
        raw_bytes = await upload.read()
        filename = upload.filename or "upload"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        source_type = SourceType.PDF if ext == "pdf" else SourceType.TEXT
        requests.append(IngestionRequest(
            input_type=IngestionInputType.FILE_BYTES,
            source_type=source_type,
            source_name=filename,
            content_bytes=raw_bytes,
            filename=filename,
            content_type=upload.content_type or "",
            entity_name=entity_name,
            tags=tag_list,
        ))

    if not requests:
        raise HTTPException(status_code=400, detail="No files provided")

    try:
        result = await workflow.run(requests, write_to_graph=write_to_graph)
    except Exception as exc:
        logger.error("File ingestion failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    summary = result["summary"]
    return IngestFilesResponse(
        status=result["status"],
        chunks_produced=summary.get("chunks_produced", 0),
        episodes_written=summary.get("episodes_written", 0),
        knowledge_sources_count=summary.get("knowledge_sources", 0),
        graph_stats=summary.get("graph_stats", {}),
        errors=summary.get("errors", []),
    )


@router.post("/ingest/url", response_model=IngestUrlResponse)
async def ingest_url(
    body: IngestUrlRequest,
    workflow: DocumentIngestionWorkflow = Depends(_get_ingestion_workflow),
):
    """Fetch a URL (or Confluence page) and ingest its content into the knowledge graph.

    Confluence URLs are detected automatically and fetched via the Confluence
    REST API when credentials are configured (env vars or request body fields).
    Any other HTTP/HTTPS URL is fetched as plain HTML and stripped to text.
    """
    try:
        result = await workflow.ingest_url(
            body.url,
            entity_name=body.entity_name,
            tags=body.tags,
            confluence_base_url=body.confluence_base_url,
            confluence_username=body.confluence_username,
            confluence_api_token=body.confluence_api_token,
            write_to_graph=body.write_to_graph,
        )
    except Exception as exc:
        logger.error("URL ingestion failed for %s: %s", body.url, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    summary = result["summary"]
    return IngestUrlResponse(
        status=result["status"],
        url=body.url,
        chunks_produced=summary.get("chunks_produced", 0),
        episodes_written=summary.get("episodes_written", 0),
        knowledge_sources_count=summary.get("knowledge_sources", 0),
        graph_stats=summary.get("graph_stats", {}),
        errors=summary.get("errors", []),
    )


@router.post("/ingest/text", response_model=IngestTextResponse)
async def ingest_text(
    body: IngestTextRequest,
    workflow: DocumentIngestionWorkflow = Depends(_get_ingestion_workflow),
):
    """Ingest a plain-text snippet (data dictionary entry, business rules, notes)
    into the knowledge graph.
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")

    try:
        result = await workflow.ingest_text(
            body.text,
            source_name=body.source_name,
            entity_name=body.entity_name,
            tags=body.tags,
            write_to_graph=body.write_to_graph,
        )
    except Exception as exc:
        logger.error("Text ingestion failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    summary = result["summary"]
    return IngestTextResponse(
        status=result["status"],
        chunks_produced=summary.get("chunks_produced", 0),
        episodes_written=summary.get("episodes_written", 0),
        knowledge_sources_count=summary.get("knowledge_sources", 0),
        graph_stats=summary.get("graph_stats", {}),
        errors=summary.get("errors", []),
    )
