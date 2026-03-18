from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional

import typer

_REPO_ROOT = Path(__file__).parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.bootstrap.chunk_builder import build_confluence_chunks, build_schema_chunks
from scripts.bootstrap.graph_writer import GraphWriter, PipelineStats, create_writer
from scripts.bootstrap.settings import BootstrapSettings
from scripts.bootstrap.source_discovery import (
    classify_confluence_file,
    discover_confluence_files,
    discover_schema_files,
    is_already_processed,
    load_bootstrap_state,
    load_confluence_file,
    load_schema_file,
    mark_processed,
    save_bootstrap_state,
)
from src.knowledge.graph.models import Chunk

app = typer.Typer(
    name="bootstrap",
    help="FinX knowledge graph bootstrap indexing pipeline (FalkorDB native)",
    no_args_is_help=True,
)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


_OPT_DRY_RUN = typer.Option(False, "--dry-run", help="Print nodes/chunks; skip graph writes")
_OPT_BATCH = typer.Option(20, "--batch-size", help="Chunks per LLM extraction batch")
_OPT_DOMAIN = typer.Option(None, "--domain", help="Filter by business domain")
_OPT_ONE_FILE = typer.Option(None, "--one-file", help="Process a single file only")
_OPT_LIMIT = typer.Option(None, "--limit", help="Max number of files to process")
_OPT_RESUME = typer.Option(True, "--resume/--no-resume", help="Skip already-processed files")
_OPT_VERBOSE = typer.Option(False, "--verbose", "-v", help="Debug logging")
_OPT_SCHEMA_DIR = typer.Option(
    "schema",
    "--schema-dir",
    help="Schema subdirectory under finx-data/output",
)
_OPT_EXTRACT = typer.Option(
    True, "--extract/--no-extract",
    help="Run LLM extraction on free-text content",
)
_OPT_UNSTRUCTURED = typer.Option(
    True, "--unstructured/--no-unstructured",
    help="Process unstructured Confluence pages via LLM extraction",
)


def _has_kg_value(sf: Any) -> bool:
    if sf.dataset:
        return bool(sf.dataset.description)
    if sf.semantic_model:
        return bool(sf.semantic_model.description)
    if not sf.table:
        return False
    t = sf.table
    if t.description or t.ai_description:
        return True
    cols = sf.columns or []
    if any(c.description for c in cols):
        return True
    return len(cols) >= 3


def _print_chunks(chunks: list[Chunk], label: str = "Chunks") -> None:
    typer.echo(f"  {label}: {len(chunks)} chunks")
    for c in chunks[:5]:
        preview = c.content[:120].replace("\n", " ")
        typer.echo(f"    [{c.id[:8]}] {preview}...")
    if len(chunks) > 5:
        typer.echo(f"    ... and {len(chunks) - 5} more")


def _process_schema(
    settings: BootstrapSettings,
    writer: GraphWriter | None,
    state: dict,
    dry_run: bool,
    domain_filter: str | None,
    one_file: str | None,
    batch_size: int,
    run_extraction: bool,
    schema_subdir: str = "schema",
) -> tuple[int, int]:
    log = logging.getLogger(__name__)
    files = discover_schema_files(settings.finx_data_output_dir, schema_subdir=schema_subdir)

    if one_file:
        one_path = settings.finx_data_output_dir / one_file
        files = [one_path] if one_path.exists() else []
        if not files:
            typer.echo(f"[WARN] File not found: {one_path}", err=True)
            return 0, 0

    n_files = 0
    n_skipped = 0
    all_chunks: list[Chunk] = []

    for path in files:
        if not one_file and settings.resume and is_already_processed(path, state):
            log.debug("Skip (already processed): %s", path.name)
            continue

        sf = load_schema_file(path)
        if not sf:
            continue

        if not _has_kg_value(sf):
            log.debug("Skip (no KG value): %s", path.name)
            n_skipped += 1
            mark_processed(path, state)
            continue

        if domain_filter:
            from scripts.bootstrap.group_id_strategy import get_schema_group_id
            gid = get_schema_group_id(sf.effective_domain, sf.table_name)
            if not gid.startswith(f"schema_{domain_filter}"):
                continue

        chunks = build_schema_chunks(sf, max_top_columns=settings.max_top_columns)

        if dry_run:
            _print_chunks(chunks, f"Schema: {path.name}")
        else:
            all_chunks.extend(chunks)

        mark_processed(path, state)
        n_files += 1

    if n_skipped:
        log.info("Schema: skipped %d low-quality files", n_skipped)
    log.info("Schema: %d files -> %d chunks", n_files, len(all_chunks))

    if not dry_run and writer and all_chunks and run_extraction:
        log.info("Schema: running LLM extraction on %d chunks", len(all_chunks))
        writer.extract_and_upsert(all_chunks, batch_size=batch_size)

    return n_files, n_skipped


def _process_confluence(
    settings: BootstrapSettings,
    writer: GraphWriter | None,
    state: dict,
    dry_run: bool,
    domain_filter: str | None,
    one_file: str | None,
    batch_size: int,
    run_extraction: bool,
    ingest_unstructured: bool,
) -> tuple[int, int]:
    log = logging.getLogger(__name__)
    files = discover_confluence_files(settings.finx_data_output_dir)

    if one_file:
        one_path = settings.finx_data_output_dir / one_file
        files = [one_path] if one_path.exists() else []
        if not files:
            typer.echo(f"[WARN] File not found: {one_path}", err=True)
            return 0, 0

    n_files = 0
    n_skipped = 0
    all_chunks: list[Chunk] = []

    for path in files:
        if not one_file and settings.resume and is_already_processed(path, state):
            log.debug("Skip (already processed): %s", path.name)
            continue

        cf = load_confluence_file(path)
        if not cf:
            continue

        kind = classify_confluence_file(cf)

        if kind == "unstructured" and not ingest_unstructured:
            log.debug("Skip unstructured (disabled): %s", path.name)
            n_skipped += 1
            continue

        chunks = build_confluence_chunks(cf)

        if not chunks:
            log.debug("Skip (no chunks): %s", path.name)
            n_skipped += 1
            continue

        if dry_run:
            _print_chunks(chunks, f"Confluence ({kind}): {path.name}")
        else:
            all_chunks.extend(chunks)

        mark_processed(path, state)
        n_files += 1

    log.info("Confluence: %d files -> %d chunks, %d skipped", n_files, len(all_chunks), n_skipped)

    if not dry_run and writer and all_chunks and run_extraction:
        log.info("Confluence: running LLM extraction on %d chunks", len(all_chunks))
        writer.extract_and_upsert(all_chunks, batch_size=batch_size)

    return n_files, n_skipped


@app.command()
def run(
    dry_run: bool = _OPT_DRY_RUN,
    batch_size: int = _OPT_BATCH,
    domain: Optional[str] = _OPT_DOMAIN,
    one_file: Optional[str] = _OPT_ONE_FILE,
    resume: bool = _OPT_RESUME,
    verbose: bool = _OPT_VERBOSE,
    extract: bool = _OPT_EXTRACT,
    unstructured: bool = _OPT_UNSTRUCTURED,
    schema_dir: str = _OPT_SCHEMA_DIR,
) -> None:
    """Run full bootstrap: schema + confluence -> FalkorDB knowledge graph."""
    _setup_logging(verbose)
    settings = BootstrapSettings(
        dry_run=dry_run,
        batch_size=batch_size,
        filter_domain=domain,
        one_file=one_file,
        resume=resume,
        ingest_unstructured_confluence=unstructured,
        schema_subdir=schema_dir,
    )
    _full_run(settings, run_schema=True, run_confluence=True, run_extraction=extract)


@app.command()
def schema(
    dry_run: bool = _OPT_DRY_RUN,
    batch_size: int = _OPT_BATCH,
    domain: Optional[str] = _OPT_DOMAIN,
    one_file: Optional[str] = _OPT_ONE_FILE,
    resume: bool = _OPT_RESUME,
    verbose: bool = _OPT_VERBOSE,
    extract: bool = _OPT_EXTRACT,
    schema_dir: str = _OPT_SCHEMA_DIR,
) -> None:
    """Bootstrap schema files only."""
    _setup_logging(verbose)
    settings = BootstrapSettings(
        dry_run=dry_run,
        batch_size=batch_size,
        filter_domain=domain,
        one_file=one_file,
        resume=resume,
        schema_subdir=schema_dir,
    )
    _full_run(settings, run_schema=True, run_confluence=False, run_extraction=extract)


@app.command()
def confluence(
    dry_run: bool = _OPT_DRY_RUN,
    batch_size: int = _OPT_BATCH,
    domain: Optional[str] = _OPT_DOMAIN,
    one_file: Optional[str] = _OPT_ONE_FILE,
    resume: bool = _OPT_RESUME,
    verbose: bool = _OPT_VERBOSE,
    extract: bool = _OPT_EXTRACT,
    unstructured: bool = _OPT_UNSTRUCTURED,
) -> None:
    """Bootstrap confluence files only."""
    _setup_logging(verbose)
    settings = BootstrapSettings(
        dry_run=dry_run,
        batch_size=batch_size,
        filter_domain=domain,
        one_file=one_file,
        resume=resume,
        ingest_unstructured_confluence=unstructured,
    )
    _full_run(settings, run_schema=False, run_confluence=True, run_extraction=extract)


@app.command()
def validate(
    domain: Optional[str] = _OPT_DOMAIN,
    one_file: Optional[str] = _OPT_ONE_FILE,
    verbose: bool = _OPT_VERBOSE,
) -> None:
    """Dry-run: print all nodes, edges, and chunks without writing."""
    _setup_logging(verbose)
    settings = BootstrapSettings(
        dry_run=True,
        filter_domain=domain,
        one_file=one_file,
        resume=False,
    )
    _full_run(settings, run_schema=True, run_confluence=True, run_extraction=True)


@app.command()
def stats(verbose: bool = _OPT_VERBOSE) -> None:
    """Show current knowledge graph statistics."""
    _setup_logging(verbose)
    settings = BootstrapSettings(dry_run=True)
    try:
        writer = create_writer(settings)
        graph_stats = writer.graph_stats
        typer.echo("\n" + "=" * 60)
        typer.echo("Knowledge Graph Statistics")
        typer.echo("=" * 60)
        typer.echo(f"  Total nodes : {graph_stats.get('nodes', 0)}")
        typer.echo(f"  Total edges : {graph_stats.get('edges', 0)}")
        labels = graph_stats.get("labels", {})
        if labels:
            typer.echo("  Node labels :")
            for label, count in sorted(labels.items(), key=lambda x: -x[1]):
                typer.echo(f"    {label:20s} : {count}")
        typer.echo("=" * 60)
        writer.close()
    except Exception as exc:
        typer.echo(f"[ERROR] Cannot connect to FalkorDB: {exc}", err=True)
        raise typer.Exit(1)


def _full_run(
    settings: BootstrapSettings,
    run_schema: bool = True,
    run_confluence: bool = True,
    run_extraction: bool = True,
) -> None:
    log = logging.getLogger(__name__)
    state = load_bootstrap_state(settings.bootstrap_state_path) if settings.resume else {}

    writer: GraphWriter | None = None
    if not settings.dry_run:
        writer = create_writer(settings)

    total_files = 0
    total_skipped = 0

    try:
        if run_schema:
            log.info("=== Stage: Schema files ===")
            nf, ns = _process_schema(
                settings=settings,
                writer=writer,
                state=state,
                dry_run=settings.dry_run,
                domain_filter=settings.filter_domain,
                one_file=settings.one_file,
                batch_size=settings.batch_size,
                run_extraction=run_extraction,
                schema_subdir=settings.schema_subdir,
            )
            total_files += nf
            total_skipped += ns

        if run_confluence:
            log.info("=== Stage: Confluence files ===")
            nf, ns = _process_confluence(
                settings=settings,
                writer=writer,
                state=state,
                dry_run=settings.dry_run,
                domain_filter=settings.filter_domain,
                one_file=settings.one_file,
                batch_size=settings.batch_size,
                run_extraction=run_extraction,
                ingest_unstructured=settings.ingest_unstructured_confluence,
            )
            total_files += nf
            total_skipped += ns

        if not settings.dry_run:
            save_bootstrap_state(settings.bootstrap_state_path, state)

    finally:
        if writer is not None:
            if writer.stats.errors:
                writer.flush_errors(settings.bootstrap_errors_path)
            writer.close()

    typer.echo("\n" + "=" * 60)
    typer.echo("Bootstrap complete")
    typer.echo(f"  Files processed : {total_files}")
    typer.echo(f"  Files skipped   : {total_skipped}")

    if settings.dry_run:
        typer.echo("  [DRY-RUN - nothing written to graph]")
    elif writer:
        typer.echo(writer.stats.summary())
        try:
            final_stats = writer.graph_stats
            typer.echo(
                f"\n  Final graph: {final_stats.get('nodes', 0)} nodes, "
                f"{final_stats.get('edges', 0)} edges"
            )
        except Exception:
            pass


if __name__ == "__main__":
    app()
