from __future__ import annotations

import os
from functools import lru_cache

from agno.db.postgres import PostgresDb

from src.knowledge.client import GraphitiClient, get_graphiti_client
from src.knowledge.entities import EntityRegistry
from src.knowledge.episodes import EpisodeStore
from src.knowledge.memory import MemoryManager
from src.knowledge.search import SemanticSearchService
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


def get_entity_registry() -> EntityRegistry:
    return get_memory().entities


def get_episode_store() -> EpisodeStore:
    return get_memory().episodes


def get_search_service() -> SemanticSearchService:
    return get_memory().search


def get_pg_db() -> PostgresDb:
    return get_postgres_db()
