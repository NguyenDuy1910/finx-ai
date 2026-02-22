from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.knowledge.graph.client import GraphitiClient
from src.knowledge.retrieval.graph_mutations import GraphMutations

logger = logging.getLogger(__name__)


class GraphExplorerService:

    def __init__(self, client: GraphitiClient):
        self._client = client
        self._mutations = GraphMutations(client)

    async def list_nodes(
        self,
        label: str,
        offset: int = 0,
        limit: int = 50,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._mutations.list_nodes(label, offset, limit, search)

    async def get_node(self, label: str, node_uuid: str) -> Optional[Dict[str, Any]]:
        return await self._mutations.get_node(label, node_uuid)

    async def create_node(
        self,
        label: str,
        name: str,
        description: str = "",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await self._mutations.create_node(label, name, description, attributes)

    async def update_node(
        self,
        label: str,
        node_uuid: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        return await self._mutations.update_node(label, node_uuid, name, description, attributes)

    async def delete_node(self, label: str, node_uuid: str) -> bool:
        return await self._mutations.delete_node(label, node_uuid)

    async def list_edges(
        self,
        source_uuid: Optional[str] = None,
        target_uuid: Optional[str] = None,
        edge_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        return await self._mutations.list_edges(source_uuid, target_uuid, edge_type, offset, limit)

    async def get_edge(self, edge_uuid: str) -> Optional[Dict[str, Any]]:
        return await self._mutations.get_edge(edge_uuid)

    async def create_edge(
        self,
        source_uuid: str,
        target_uuid: str,
        edge_type: str,
        fact: str = "",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await self._mutations.create_edge(source_uuid, target_uuid, edge_type, fact, attributes)

    async def update_edge(
        self,
        edge_uuid: str,
        fact: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        return await self._mutations.update_edge(edge_uuid, fact, attributes)

    async def delete_edge(self, edge_uuid: str) -> bool:
        return await self._mutations.delete_edge(edge_uuid)

    async def explore_node(self, node_uuid: str) -> Optional[Dict[str, Any]]:
        return await self._mutations.explore_node(node_uuid)

    async def expand_node(self, node_uuid: str) -> Optional[Dict[str, Any]]:
        return await self._mutations.expand_node(node_uuid)

    async def get_lineage(self, node_uuid: str) -> Dict[str, Any]:
        return await self._mutations.get_lineage(node_uuid)

    async def get_overview(self) -> Dict[str, Any]:
        return await self._mutations.get_overview()

    async def search_nodes(
        self,
        query: str,
        label: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        return await self._mutations.search_nodes(query, label, limit)

    async def search_nodes_by_embedding(
        self,
        query: str,
        label: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        return await self._mutations.search_nodes_by_embedding(query, label, limit)
