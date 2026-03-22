"""CLI entry point for the preprocessing pipeline.

Usage:
    uv run python -m pipeline.cli confluence --space DAFinX --output output/pipeline
    uv run python -m pipeline.cli confluence --space DAFinX --include-comments --include-attachments --incremental
    uv run python -m pipeline.cli jira --project DATA FINX --output output/pipeline
    uv run python -m pipeline.cli jira --jql "project = DATA AND status = Done" --incremental
    uv run python -m pipeline.cli local --dir input/schemas --output output/pipeline
    uv run python -m pipeline.cli qdrant-chunks --chunks-dir output/chunks
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pipeline.engine import run_pipeline


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--output", "-o", default="output/pipeline", help="Output directory")
    common.add_argument("--format", "-f", choices=["canonical"], default="canonical")
    common.add_argument("--use-llm", action="store_true", help="Enable LLM normalization")
    common.add_argument("--llm-model", default=None, help="Override LLM model name")
    common.add_argument("--llm-concurrency", type=int, default=4, help="Concurrent LLM calls (default: 4)")
    common.add_argument("--use-docling", action="store_true", default=True, help="Use Docling extraction (default: enabled)")
    common.add_argument("--min-words", type=int, default=10, help="Skip docs with fewer words (default: 10)")
    common.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    common.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    # Chunking flags
    common.add_argument("--enable-chunking", action="store_true", help="Enable chunking stage (produces ChunkDocument JSON)")
    common.add_argument("--chunk-output-dir", default=None, help="Output directory for chunk JSON (default: <output>/chunks)")
    common.add_argument("--max-chunk-tokens", type=int, default=400, help="Max tokens per chunk (default: 400)")
    common.add_argument("--chunk-overlap", type=int, default=50, help="Token overlap between chunks (default: 50)")
    common.add_argument("--tenant-id", default="default", help="Tenant ID for chunks (default: 'default')")
    common.add_argument("--artifact-store", default="local", choices=["local", "s3"],
                        help="Artifact storage backend for attachments (default: local)")
    common.add_argument("--s3-bucket", default=None, help="S3 bucket for artifact storage (when --artifact-store=s3)")
    common.add_argument("--s3-prefix", default=None, help="S3 key prefix (default: 'artifacts')")
    common.add_argument("--s3-endpoint", default=None, help="S3 endpoint URL for MinIO / LocalStack")

    parser = argparse.ArgumentParser(prog="finx-data-pipeline", description="Document preprocessing pipeline")
    sub = parser.add_subparsers(dest="source", required=True)

    conf = sub.add_parser("confluence", parents=[common], help="Process Confluence pages")
    conf.add_argument("--space", nargs="+", help="Confluence space key(s)")
    conf.add_argument("--url", help="Process a single page by URL")
    conf.add_argument("--limit", type=int, default=2000, help="Max pages per space")
    conf.add_argument("--include-comments", action="store_true", help="Also ingest Confluence comments")
    conf.add_argument("--include-attachments", action="store_true", help="Also ingest Confluence attachments")
    conf.add_argument("--include-blogposts", action="store_true", help="Also ingest blog posts")
    conf.add_argument("--body-format", default="storage", choices=["storage", "atlas_doc_format", "export_view"],
                       help="Confluence body representation (default: storage)")
    conf.add_argument("--incremental", action="store_true", help="Use incremental sync (only fetch changed content)")
    conf.add_argument("--sync-state-file", default=".confluence_sync_state.json",
                       help="Path to Confluence sync state file (default: .confluence_sync_state.json)")

    jira = sub.add_parser("jira", parents=[common], help="Process Jira issues")
    jira.add_argument("--project", nargs="+", help="Jira project key(s)")
    jira.add_argument("--jql", help="Custom JQL query (overrides --project)")
    jira.add_argument("--include-comments", action="store_true", default=True,
                      help="Include issue comments (default: True)")
    jira.add_argument("--include-attachments", action="store_true", help="Also ingest issue attachments")
    jira.add_argument("--incremental", action="store_true", help="Use incremental sync")
    jira.add_argument("--sync-state-file", default=".jira_sync_state.json",
                      help="Path to Jira sync state file (default: .jira_sync_state.json)")

    local = sub.add_parser("local", parents=[common], help="Process local files")
    local.add_argument("--dir", required=True, help="Input directory")
    local.add_argument("--glob", nargs="+", default=None, help="File glob patterns")

    # Chunk-level Qdrant ingest
    chunk_ingest = sub.add_parser("qdrant-chunks", help="Ingest chunk JSON files into Qdrant (chunk-per-point)")
    chunk_ingest.add_argument("--chunks-dir", default="output/chunks", help="Directory with ChunkDocument JSON files")
    chunk_ingest.add_argument("--qdrant-url", default=None)
    chunk_ingest.add_argument("--api-key", default=None)
    chunk_ingest.add_argument("--collection", default="finx_chunks")
    chunk_ingest.add_argument("--embedding-model", default=None)
    chunk_ingest.add_argument("--embedding-dim", type=int, default=None)
    chunk_ingest.add_argument("--batch-size", type=int, default=100)
    chunk_ingest.add_argument("--overwrite", action="store_true")
    chunk_ingest.add_argument("--dry-run", action="store_true")
    chunk_ingest.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(message)s")

    if args.source == "qdrant-chunks":
        from pipeline.ingest.chunk_ingest import ChunkIngestionPipeline, ChunkIngestConfig

        cfg = ChunkIngestConfig(
            chunks_dir=args.chunks_dir,
            collection_name=args.collection,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
        if args.qdrant_url:
            cfg.qdrant_url = args.qdrant_url
        if args.api_key:
            cfg.qdrant_api_key = args.api_key
        if args.embedding_model:
            cfg.embedding_model = args.embedding_model
        if args.embedding_dim:
            cfg.embedding_dim = args.embedding_dim

        pipeline = ChunkIngestionPipeline(config=cfg)
        result = pipeline.run()
        sys.exit(1 if result.failed > 0 else 0)
        return

    # Set up artifact store from CLI flag
    import os
    artifact_store_type = getattr(args, "artifact_store", "local")
    os.environ.setdefault("ARTIFACT_STORE_TYPE", artifact_store_type)
    # Forward S3 CLI args to env vars so the factory picks them up
    if artifact_store_type == "s3":
        if getattr(args, "s3_bucket", None):
            os.environ.setdefault("S3_ARTIFACT_BUCKET", args.s3_bucket)
        if getattr(args, "s3_prefix", None):
            os.environ.setdefault("S3_ARTIFACT_PREFIX", args.s3_prefix)
        if getattr(args, "s3_endpoint", None):
            os.environ.setdefault("S3_ENDPOINT_URL", args.s3_endpoint)

    from pipeline.storage import create_artifact_store
    artifact_store = create_artifact_store()

    if args.source == "confluence":
        from pipeline.adapters.confluence import ConfluenceAdapter
        progress_file = Path(args.output) / ".pipeline_progress.json"
        adapter = ConfluenceAdapter(
            space_keys=args.space,
            include_comments=getattr(args, "include_comments", False),
            include_attachments=getattr(args, "include_attachments", False),
            include_blogposts=getattr(args, "include_blogposts", False),
            body_format=getattr(args, "body_format", "storage"),
            artifact_store=artifact_store,
            page_url=getattr(args, "url", None),
            limit=getattr(args, "limit", 2000),
            progress_file=progress_file,
        )
        if getattr(args, "incremental", False):
            from pipeline.adapters.confluence_sync import ConfluenceSyncAdapter
            adapter = ConfluenceSyncAdapter(
                inner=adapter,
                state_path=getattr(args, "sync_state_file", ".confluence_sync_state.json"),
            )
    elif args.source == "jira":
        from pipeline.adapters.jira import JiraAdapter
        adapter = JiraAdapter(
            project_keys=getattr(args, "project", None),
            jql=getattr(args, "jql", None),
            include_comments=getattr(args, "include_comments", True),
            include_attachments=getattr(args, "include_attachments", False),
            artifact_store=artifact_store,
        )
        if getattr(args, "incremental", False):
            from pipeline.adapters.jira_sync import JiraSyncAdapter
            adapter = JiraSyncAdapter(
                inner=adapter,
                state_path=getattr(args, "sync_state_file", ".jira_sync_state.json"),
            )
    elif args.source == "local":
        from pipeline.adapters.local import LocalFileAdapter
        adapter = LocalFileAdapter(args.dir)
    else:
        parser.error(f"Unknown source: {args.source}")
        return

    result = run_pipeline(
        adapter,
        output_dir=args.output,
        use_llm=args.use_llm,
        use_docling=args.use_docling,
        llm_model=args.llm_model,
        llm_concurrency=args.llm_concurrency,
        min_doc_words=args.min_words,
        format=args.format,
        overwrite=args.overwrite,
        enable_chunking=args.enable_chunking,
        chunk_output_dir=args.chunk_output_dir,
        max_chunk_tokens=args.max_chunk_tokens,
        chunk_overlap_tokens=args.chunk_overlap,
        default_tenant_id=args.tenant_id,
    )
    sys.exit(1 if result.total_errors > 0 and result.total_processed == 0 else 0)


if __name__ == "__main__":
    main()
