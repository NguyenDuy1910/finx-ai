"""Knowledge graph evaluation — quality metrics, extraction eval, retrieval eval.

Modules
-------
metrics.py          — graph structural quality (orphans, coverage, connectivity)
extraction_eval.py  — extraction precision/recall vs ground truth
retrieval_eval.py   — retrieval hit-rate, MRR, context relevance
runner.py           — CLI entrypoint for running evaluations
"""
from __future__ import annotations

from .metrics import GraphMetrics, GraphQualityReport
from .extraction_eval import ExtractionEvaluator, ExtractionScore
from .retrieval_eval import RetrievalEvaluator, RetrievalScore

__all__ = [
    "GraphMetrics",
    "GraphQualityReport",
    "ExtractionEvaluator",
    "ExtractionScore",
    "RetrievalEvaluator",
    "RetrievalScore",
]
