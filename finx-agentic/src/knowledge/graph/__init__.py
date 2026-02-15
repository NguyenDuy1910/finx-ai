from src.knowledge.graph.client import GraphitiClient, get_graphiti_client
from src.knowledge.graph.cost_tracker import GraphCostTracker, EmbeddingCall

# Schemas re-exports (canonical location: graph.schemas)
from src.knowledge.graph.schemas import BaseNode, BaseEdge
from src.knowledge.graph.schemas.enums import NodeLabel
from src.knowledge.graph.schemas.nodes import (
    TableNode, ColumnNode, BusinessEntityNode,
    QueryPatternNode, DomainNode, BusinessRuleNode, CodeSetNode,
)
from src.knowledge.graph.schemas.edges import (
    EdgeType,
    HasColumnEdge, JoinEdge, EntityMappingEdge, QueryPatternEdge,
    ForeignKeyEdge, SynonymEdge, BelongsToDomainEdge, ContainsEntityEdge,
    HasRuleEdge, AppliesToEdge, ColumnMappingEdge, HasCodeSetEdge, DerivedFromEdge,
)
from src.knowledge.graph.schemas.episodes import (
    EpisodeCategory, SchemaEpisode, QueryEpisode, FeedbackEpisode, PatternEpisode,
)

# Backward-compat alias: GraphLoader → SchemaIndexer
from src.knowledge.indexing.schema_indexer import SchemaIndexer
GraphLoader = SchemaIndexer  # deprecated alias

__all__ = [
    "GraphitiClient",
    "get_graphiti_client",
    "GraphLoader",
    "GraphCostTracker",
    "EmbeddingCall",
    # schemas
    "BaseNode",
    "BaseEdge",
    "NodeLabel",
    "TableNode",
    "ColumnNode",
    "BusinessEntityNode",
    "QueryPatternNode",
    "DomainNode",
    "BusinessRuleNode",
    "CodeSetNode",
    "EdgeType",
    "HasColumnEdge",
    "JoinEdge",
    "EntityMappingEdge",
    "QueryPatternEdge",
    "ForeignKeyEdge",
    "SynonymEdge",
    "BelongsToDomainEdge",
    "ContainsEntityEdge",
    "HasRuleEdge",
    "AppliesToEdge",
    "ColumnMappingEdge",
    "HasCodeSetEdge",
    "DerivedFromEdge",
    "EpisodeCategory",
    "SchemaEpisode",
    "QueryEpisode",
    "FeedbackEpisode",
    "PatternEpisode",
    # indexing alias
    "SchemaIndexer",
]
