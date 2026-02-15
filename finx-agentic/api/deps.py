from __future__ import annotations

import os
from functools import lru_cache

from agno.db.postgres import PostgresDb

from src.knowledge.graph.client import GraphitiClient, get_graphiti_client
from src.knowledge.indexing.entity_indexer import EntityIndexer
from src.knowledge.indexing.episode_indexer import EpisodeIndexer
from src.knowledge.memory import MemoryManager
from src.knowledge.retrieval.schema_retrieval import SchemaRetrievalService
from src.storage.postgres import get_postgres_db


@lru_cache(maxsize=1)
def get_client() -> GraphitiClient:
    return get_graphiti_client(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
    )


@lru_cache(maxsize=1)
def get_memory() -> MemoryManager:
    return MemoryManager(get_client())


def get_entity_registry() -> EntityIndexer:
    return get_memory().entities


def get_episode_store() -> EpisodeIndexer:
    return get_memory().episodes


def get_search_service() -> SchemaRetrievalService:
    return get_memory().search


def get_pg_db() -> PostgresDb:
    return get_postgres_db()
