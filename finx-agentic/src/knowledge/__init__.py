"""knowledge — backward-compatible re-exports from restructured sub-packages.

New canonical locations
-----------------------
graph/schemas/  BaseNode, BaseEdge, node/edge/episode models
graph/          GraphitiClient, get_graphiti_client, GraphCostTracker
indexing/       SchemaIndexer, EntityIndexer, EpisodeIndexer
retrieval/      SchemaRetrievalService, EntityQueries, EpisodeQueries,
                SearchReranker, models
utils/          SessionFileLogger
"""

# ── graph ────────────────────────────────────────────────────────────
from src.knowledge.graph import (
    GraphitiClient,
    get_graphiti_client,
    GraphCostTracker,
    EmbeddingCall,
)

# ── indexing (write path) ────────────────────────────────────────────
from src.knowledge.indexing import SchemaIndexer, EntityIndexer, EpisodeIndexer

# Backward-compat aliases
GraphLoader = SchemaIndexer
EntityRegistry = EntityIndexer
EpisodeStore = EpisodeIndexer

# ── retrieval (read path) ───────────────────────────────────────────
from src.knowledge.retrieval import (
    SchemaRetrievalService,
    EntityQueries,
    EpisodeQueries,
    SearchResult,
    SchemaSearchResult,
    TableContext,
    SearchReranker,
    ScoredItem,
    RerankerWeights,
    INTENT_WEIGHT_PROFILES,
    weights_for_intent,
)

# ── utils ────────────────────────────────────────────────────────────
from src.knowledge.utils import SessionFileLogger, track_class

# ── memory façade ────────────────────────────────────────────────────
from src.knowledge.memory import MemoryManager

# ── constants ────────────────────────────────────────────────────────
from src.knowledge.constants import DEFAULT_GROUP_ID, DEFAULT_TOP_K, DEFAULT_SIMILARITY_THRESHOLD

# ── models (canonical: graph.schemas) ───────────────────────────────
from src.knowledge.graph.schemas import BaseNode, BaseEdge
from src.knowledge.graph.schemas.nodes import (
    TableNode,
    ColumnNode,
    BusinessEntityNode,
    QueryPatternNode,
    DomainNode,
    BusinessRuleNode,
    CodeSetNode,
)
from src.knowledge.graph.schemas.enums import NodeLabel
from src.knowledge.graph.schemas.edges import (
    EdgeType,
    HasColumnEdge,
    JoinEdge,
    EntityMappingEdge,
    QueryPatternEdge,
    ForeignKeyEdge,
    SynonymEdge,
    BelongsToDomainEdge,
    ContainsEntityEdge,
    HasRuleEdge,
    AppliesToEdge,
    ColumnMappingEdge,
    HasCodeSetEdge,
    DerivedFromEdge,
)
from src.knowledge.graph.schemas.episodes import (
    EpisodeCategory,
    SchemaEpisode,
    QueryEpisode,
    FeedbackEpisode,
    PatternEpisode,
)


__all__ = [
    # graph
    "get_graphiti_client",
    "GraphitiClient",
    "GraphCostTracker",
    "EmbeddingCall",
    # indexing (write path)
    "SchemaIndexer",
    "EntityIndexer",
    "EpisodeIndexer",
    # backward-compat aliases
    "GraphLoader",
    "EntityRegistry",
    "EpisodeStore",
    # retrieval (read path)
    "SchemaRetrievalService",
    "EntityQueries",
    "EpisodeQueries",
    # memory
    "MemoryManager",
    # search models
    "SearchResult",
    "SchemaSearchResult",
    "TableContext",
    # reranker
    "SearchReranker",
    "ScoredItem",
    "RerankerWeights",
    "INTENT_WEIGHT_PROFILES",
    "weights_for_intent",
    # utils
    "SessionFileLogger",
    "track_class",
    # constants
    "DEFAULT_GROUP_ID",
    "DEFAULT_TOP_K",
    "DEFAULT_SIMILARITY_THRESHOLD",
    # base models
    "BaseNode",
    "BaseEdge",
    # node models
    "NodeLabel",
    "TableNode",
    "ColumnNode",
    "BusinessEntityNode",
    "QueryPatternNode",
    "DomainNode",
    "BusinessRuleNode",
    "CodeSetNode",
    # edge models
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
    # episode models
    "EpisodeCategory",
    "SchemaEpisode",
    "QueryEpisode",
    "FeedbackEpisode",
    "PatternEpisode",
]
