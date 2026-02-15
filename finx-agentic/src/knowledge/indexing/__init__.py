"""indexing — write-path for the knowledge graph.

Sub-modules
-----------
schema_indexer   SchemaIndexer (JSON dir → graph, was graph/loader.py)
entity_indexer   EntityIndexer (upsert nodes/edges, was registry/entity_registry.py)
episode_indexer  EpisodeIndexer (store episodes, was registry/episode_store.py write-side)
"""

from src.knowledge.indexing.schema_indexer import SchemaIndexer
from src.knowledge.indexing.entity_indexer import EntityIndexer
from src.knowledge.indexing.episode_indexer import EpisodeIndexer

__all__ = [
    "SchemaIndexer",
    "EntityIndexer",
    "EpisodeIndexer",
]
