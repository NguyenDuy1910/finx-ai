from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import typer

from src.knowledge.graph.client import FalkorDBClient
from src.knowledge.graph.store import GraphStore

from .metrics import GraphMetrics
from .extraction_eval import ExtractionEvaluator
from .retrieval_eval import RetrievalEvaluator

logger = logging.getLogger(__name__)
app = typer.Typer(name="kg-eval", help="Knowledge graph evaluation CLI.")


def _get_client() -> FalkorDBClient:
    return FalkorDBClient(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        graph_name=os.getenv("FALKORDB_GRAPH", "finx_knowledge"),
    )


def _build_extractor() -> Any:
    from src.knowledge.graph.extractor import Extractor
    from src.core.llm import create_llm_adapter

    provider = os.getenv("LLM_PROVIDER", "openai")
    api_key = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    model = os.getenv("LLM_MODEL", "gpt-4.1-mini")
    base_url = os.getenv("LLM_BASE_URL") or None

    llm = create_llm_adapter(provider, api_key, model, base_url=base_url)
    return Extractor(llm, gleaning_rounds=0, max_concurrent=5)


@app.command()
def quality() -> None:
    """Run graph structural quality metrics against the live graph."""
    logging.basicConfig(level=logging.WARNING)

    client = _get_client()
    metrics = GraphMetrics(client)
    report = metrics.evaluate()

    typer.echo(report.summary())
    client.close()


@app.command()
def retrieval(
    queries: str = typer.Option(
        None, "--queries", "-q",
        help="Path to JSON file with test queries.",
    ),
) -> None:
    """Evaluate retrieval quality (hit-rate, MRR, precision, recall).

    If no --queries file is provided, runs a built-in smoke test.
    """
    logging.basicConfig(level=logging.WARNING)

    client = _get_client()
    store = GraphStore(client)
    evaluator = RetrievalEvaluator(store)

    if queries:
        data = json.loads(Path(queries).read_text(encoding="utf-8"))
        evaluator.load_queries_json(data)
    else:
        evaluator.add_query(
            query="deposit transaction",
            expected_nodes=["DM_DEPOSIT_TXN"],
            expected_neighbors=["DEPOSITS"],
        )
        evaluator.add_query(
            query="customer",
            expected_nodes=["CUSTOMERS"],
        )
        typer.echo("Using built-in smoke test queries (use --queries for custom)")

    score = evaluator.evaluate()
    typer.echo(score.summary())
    client.close()


@app.command()
def extraction(
    ground_truth: str = typer.Option(
        ..., "--ground-truth", "-g",
        help="Path to JSON file with expected entities/edges per chunk.",
    ),
    source: str = typer.Option(
        "schema", "--source", "-s",
        help="Source to run extraction against: schema | confluence",
    ),
) -> None:
    """Evaluate extraction quality (precision, recall, F1) vs ground truth."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from src.knowledge.indexing.sources.schema_source import SchemaSource
    from src.knowledge.indexing.sources.confluence_source import ConfluenceSource

    gt_data = json.loads(Path(ground_truth).read_text(encoding="utf-8"))
    evaluator = ExtractionEvaluator()
    evaluator.load_ground_truth_json(gt_data)

    data_dir = Path(os.getenv(
        "FINX_DATA_OUTPUT_DIR",
        str(Path(__file__).parents[5] / "finx-data" / "output"),
    ))

    if source == "schema":
        src = SchemaSource(data_dir)
    elif source == "confluence":
        src = ConfluenceSource(data_dir)
    else:
        typer.echo(f"Unknown source: {source}", err=True)
        raise typer.Exit(1)

    extractor = _build_extractor()
    all_results = []

    for doc in src.discover():
        chunks = src.to_chunks(doc)
        if chunks:
            results = extractor.extract_batch(chunks)
            all_results.extend(results)

    score = evaluator.evaluate(all_results)
    typer.echo(score.summary())


@app.command(name="all")
def run_all(
    queries: str = typer.Option(None, "--queries", "-q", help="Retrieval queries JSON"),
    ground_truth: str = typer.Option(None, "--ground-truth", "-g", help="Extraction ground truth JSON"),
) -> None:
    """Run all evaluations: quality + retrieval + extraction (if data provided)."""
    logging.basicConfig(level=logging.WARNING)

    client = _get_client()

    typer.echo("\nGraph Quality Metrics")
    metrics = GraphMetrics(client)
    report = metrics.evaluate()
    typer.echo(report.summary())

    typer.echo("\nRetrieval Evaluation")
    store = GraphStore(client)
    ret_evaluator = RetrievalEvaluator(store)
    if queries:
        data = json.loads(Path(queries).read_text(encoding="utf-8"))
        ret_evaluator.load_queries_json(data)
    else:
        ret_evaluator.add_query(query="deposit transaction", expected_nodes=["DM_DEPOSIT_TXN"])
        ret_evaluator.add_query(query="customer", expected_nodes=["CUSTOMERS"])
        typer.echo("  Using built-in smoke test queries")
    ret_score = ret_evaluator.evaluate()
    typer.echo(ret_score.summary())

    if ground_truth:
        typer.echo("\nExtraction Evaluation")
        typer.echo("  Running extractor...")
        extraction(ground_truth=ground_truth, source="schema")
    else:
        typer.echo("\nExtraction Evaluation — skipped (no --ground-truth provided)")

    client.close()


if __name__ == "__main__":
    app()
