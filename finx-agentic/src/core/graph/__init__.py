"""core.graph — Graphiti infrastructure layer.

Provides:
  GraphitiClient  — thin wrapper over graphiti_core.Graphiti
  GraphitiWriter  — bulk/single episode writer with fallback
  ontology        — entity types, edge types, extraction config
"""

from src.core.graph.client import GraphitiClient, get_graphiti_client
from src.core.graph.ontology import ENTITY_TYPES, EDGE_TYPES, EDGE_TYPE_MAP

__all__ = [
    "GraphitiClient",
    "get_graphiti_client",
    "ENTITY_TYPES",
    "EDGE_TYPES",
    "EDGE_TYPE_MAP",
]
