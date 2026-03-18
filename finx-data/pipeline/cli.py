"""CLI entry point for the preprocessing pipeline.

Usage
-----
    # Process Confluence pages
    uv run python -m pipeline.cli confluence --space DAFinX --output output/pipeline

    # Process local files
    uv run python -m pipeline.cli local --dir input/schemas --output output/pipeline

    # Process with LLM normalization + raw artifact storage
    uv run python -m pipeline.cli confluence --space DAFinX --use-llm --save-raw --output output/pipeline

    # Process Athena schemas
    uv run python -m pipeline.cli athena --database my_db --output output/pipeline

    # Process S3 documents
    uv run python -m pipeline.cli s3 --bucket my-bucket --prefix docs/ --output output/pipeline

    # Re-process from stored raw artifacts (no re-fetching)
    uv run python -m pipeline.cli reprocess --raw-dir output/pipeline/raw_artifacts --output output/pipeline

    # Ingest knowledge files into Qdrant
    uv run python -m pipeline.cli qdrant --knowledge-dir output/knowledge
    uv run python -m pipeline.cli qdrant --knowledge-dir output/knowledge --dry-run
    uv run python -m pipeline.cli qdrant --knowledge-dir output/knowledge --overwrite
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pipeline.engine import PipelineConfig, PipelineEngine, run_pipeline


def _build_parser() -> argparse.ArgumentParser:
    # Shared arguments inherited by every subcommand
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--output", "-o",
        default="output/pipeline",
        help="Output directory (default: output/pipeline)",
    )
    common.add_argument(
        "--format", "-f",
        choices=["canonical", "legacy", "knowledge"],
        default="canonical",
        help="Output format: canonical (full), legacy (bootstrap-compat), knowledge (Qdrant-ready)",
    )
    common.add_argument("--use-llm", action="store_true", help="Enable LLM normalization (Stage 6)")
    common.add_argument("--llm-model", default=None, help="Override LLM model name")
    common.add_argument("--llm-concurrency", type=int, default=4, help="Concurrent LLM normalization calls (default: 4)")
    common.add_argument("--use-docling", action="store_true", help="Use Docling for PDF/DOCX/PPTX/XLSX extraction (Stage 5)")
    common.add_argument("--min-words", type=int, default=10, help="Skip documents with fewer words than this (default: 10)")
    common.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    common.add_argument("--save-intermediate", action="store_true", help="Save intermediate files after each stage (step1_extracted, step2_normalized)")
    common.add_argument("--intermediate-dir", default=None, help="Directory for intermediate files (default: <output>/intermediate)")
    common.add_argument("--save-raw", action="store_true", help="Persist raw artifacts to disk (Stage 3: Raw Artifact Store)")
    common.add_argument("--raw-dir", default=None, help="Directory for raw artifact store (default: <output>/raw_artifacts)")
    common.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    parser = argparse.ArgumentParser(
        prog="finx-data-pipeline",
        description="Enterprise 7-stage preprocessing pipeline for document ingestion",
    )
    sub = parser.add_subparsers(dest="source", required=True)

    # Confluence
    conf = sub.add_parser("confluence", parents=[common], help="Process Confluence pages")
    conf.add_argument("--space", nargs="+", help="Confluence space key(s)")
    conf.add_argument("--url", help="Process a single page by URL")
    conf.add_argument("--limit", type=int, default=2000, help="Max pages per space")

    # Local files
    local = sub.add_parser("local", parents=[common], help="Process local files")
    local.add_argument("--dir", required=True, help="Input directory")
    local.add_argument("--glob", nargs="+", default=None, help="File glob patterns")

    # Athena
    ath = sub.add_parser("athena", parents=[common], help="Process Athena/Glue schemas")
    ath.add_argument("--database", help="Athena database name")
    ath.add_argument("--concurrency", type=int, default=None, help="Parallel workers")

    # S3
    s3p = sub.add_parser("s3", parents=[common], help="Process S3 documents")
    s3p.add_argument("--bucket", help="S3 bucket name")
    s3p.add_argument("--prefix", default="", help="S3 key prefix")
    s3p.add_argument("--max-objects", type=int, default=0, help="Max objects to fetch")

    # Reprocess from stored raw artifacts
    sub.add_parser("reprocess", parents=[common], help="Re-process from stored raw artifacts (no re-fetching)")

    # Qdrant ingestion (standalone subcommand — does not share common pipeline args)
    qdrant_p = sub.add_parser(
        "qdrant",
        help="Ingest output/knowledge files into Qdrant as vector embeddings",
    )
    qdrant_p.add_argument(
        "--knowledge-dir",
        default="output/knowledge",
        help="Directory containing knowledge JSON files (default: output/knowledge)",
    )
    qdrant_p.add_argument(
        "--qdrant-url",
        default=None,
        help="Qdrant server URL (default: $QDRANT_URL or http://localhost:6333)",
    )
    qdrant_p.add_argument(
        "--api-key",
        default=None,
        help="Qdrant API key (default: $QDRANT_API_KEY)",
    )
    qdrant_p.add_argument(
        "--collection",
        default=None,
        help="Qdrant collection name (default: $QDRANT_COLLECTION or finx_knowledge)",
    )
    qdrant_p.add_argument(
        "--embedding-model",
        default=None,
        help="OpenAI embedding model (default: $EMBEDDING_MODEL or text-embedding-3-small)",
    )
    qdrant_p.add_argument(
        "--embedding-dim",
        type=int,
        default=None,
        help="Expected embedding vector dimension (default: 1536 for text-embedding-3-small)",
    )
    qdrant_p.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Points per Qdrant upsert call (default: 100)",
    )
    qdrant_p.add_argument(
        "--min-quality",
        type=float,
        default=0.0,
        help="Skip documents with quality_score below this threshold (default: 0.0)",
    )
    qdrant_p.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-embed and overwrite even when content has not changed",
    )
    qdrant_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without writing anything to Qdrant",
    )
    qdrant_p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(message)s",
    )

    # Handle qdrant subcommand (independent of the preprocessing pipeline)
    if args.source == "qdrant":
        from pipeline.ingest.config import QdrantIngestConfig
        from pipeline.ingest.pipeline import QdrantIngestionPipeline

        cfg = QdrantIngestConfig(
            knowledge_dir=args.knowledge_dir,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            min_quality_score=args.min_quality,
        )
        # CLI args override env-var defaults
        if args.qdrant_url:
            cfg.qdrant_url = args.qdrant_url
        if args.api_key:
            cfg.qdrant_api_key = args.api_key
        if args.collection:
            cfg.collection_name = args.collection
        if args.embedding_model:
            cfg.embedding_model = args.embedding_model
        if args.embedding_dim:
            cfg.embedding_dim = args.embedding_dim

        pipeline = QdrantIngestionPipeline(config=cfg)
        result = pipeline.run()
        sys.exit(1 if result.failed > 0 else 0)
        return

    # Handle reprocess subcommand (no adapter needed)
    if args.source == "reprocess":
        from pipeline.writers.json_writer import JSONWriter, ProgressTrackingWriter

        config = PipelineConfig(
            use_llm_normalizer=args.use_llm,
            llm_model=args.llm_model,
            use_docling=args.use_docling,
            save_intermediate=args.save_intermediate,
            intermediate_dir=args.intermediate_dir or Path(args.output) / "intermediate",
            raw_artifact_dir=args.raw_dir or Path(args.output) / "raw_artifacts",
        )
        json_writer = JSONWriter(args.output, format=args.format, overwrite=args.overwrite)
        progress_file = Path(args.output) / ".pipeline_progress.json"
        writer = ProgressTrackingWriter(json_writer, progress_file)

        engine = PipelineEngine(config=config, writer=writer)
        result = engine.reprocess()
        sys.exit(1 if result.total_errors > 0 and result.total_processed == 0 else 0)
        return

    # Build adapter
    if args.source == "confluence":
        from pipeline.adapters.confluence import ConfluenceAdapter

        adapter = ConfluenceAdapter(space_keys=args.space)
        kwargs = {"page_url": args.url, "limit": args.limit} if args.url else {"limit": args.limit}

    elif args.source == "local":
        from pipeline.adapters.local import LocalFileAdapter

        adapter = LocalFileAdapter(args.dir)
        kwargs = {"globs": args.glob} if args.glob else {}

    elif args.source == "athena":
        from pipeline.adapters.athena import AthenaSchemaAdapter

        adapter = AthenaSchemaAdapter(database=args.database, concurrency=args.concurrency)
        kwargs = {}

    elif args.source == "s3":
        from pipeline.adapters.s3 import S3Adapter

        adapter = S3Adapter(bucket=args.bucket, prefix=args.prefix)
        kwargs = {"max_objects": args.max_objects}

    else:
        parser.error(f"Unknown source: {args.source}")
        return

    result = run_pipeline(
        adapter,
        output_dir=args.output,
        use_llm=args.use_llm,
        use_docling=args.use_docling,
        save_intermediate=args.save_intermediate,
        intermediate_dir=args.intermediate_dir,
        llm_model=args.llm_model,
        llm_concurrency=args.llm_concurrency,
        min_doc_words=args.min_words,
        format=args.format,
        overwrite=args.overwrite,
        save_raw_artifacts=args.save_raw,
        raw_artifact_dir=args.raw_dir,
    )

    sys.exit(1 if result.total_errors > 0 and result.total_processed == 0 else 0)


if __name__ == "__main__":
    main()
