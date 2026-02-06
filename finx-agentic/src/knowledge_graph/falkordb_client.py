import logging
from typing import Any, Dict, List, Optional
from functools import lru_cache

try:
    from falkordb import FalkorDB
except ImportError:
    raise ImportError(
        "falkordb is required. Install with: pip install graphiti-core[falkordb]"
    )

logger = logging.getLogger(__name__)


class FalkorDBClient:
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        username: Optional[str] = None,
        password: Optional[str] = None,
        graph_name: str = "text2sql_knowledge"
    ):
        """
        Initialize FalkorDB client.
        
        Args:
            host: FalkorDB host address
            port: FalkorDB port
            username: Optional username for authentication
            password: Optional password for authentication
            graph_name: Name of the graph to use
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.graph_name = graph_name
        self._client: Optional[FalkorDB] = None
        self._graph = None
        
    @property
    def client(self) -> FalkorDB:
        """Get or create FalkorDB client connection."""
        if self._client is None:
            self._connect()
        return self._client
    
    @property
    def graph(self):
        """Get the graph instance."""
        if self._graph is None:
            self._graph = self.client.select_graph(self.graph_name)
        return self._graph
    
    def _connect(self) -> None:
        """Establish connection to FalkorDB."""
        try:
            self._client = FalkorDB(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password
            )
            logger.info(f"Connected to FalkorDB at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to FalkorDB: {e}")
            raise
    
    def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results.
        
        Args:
            query: Cypher query string
            params: Optional query parameters
            
        Returns:
            List of result dictionaries
        """
        try:
            if params:
                result = self.graph.query(query, params)
            else:
                result = self.graph.query(query)

            if result.result_set:
                raw_headers = result.header
                headers = []
                for h in raw_headers:
                    if isinstance(h, list):
                        headers.append(h[1] if len(h) > 1 else str(h[0]))
                    else:
                        headers.append(str(h))
                return [
                    dict(zip(headers, row))
                    for row in result.result_set
                ]
            return []

        except Exception as e:
            logger.error(f"Query execution failed: {e}\nQuery: {query}")
            raise
    
    def execute_write(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a write query (CREATE, MERGE, DELETE, etc.).
        
        Args:
            query: Cypher query string
            params: Optional query parameters
            
        Returns:
            Statistics about the operation
        """
        try:
            if params:
                result = self.graph.query(query, params)
            else:
                result = self.graph.query(query)
            
            return {
                "nodes_created": result.nodes_created,
                "nodes_deleted": result.nodes_deleted,
                "relationships_created": result.relationships_created,
                "relationships_deleted": result.relationships_deleted,
                "properties_set": result.properties_set,
            }
        except Exception as e:
            logger.error(f"Write execution failed: {e}\nQuery: {query}")
            raise
    
    def close(self) -> None:
        """Close the database connection."""
        if self._client:
            # FalkorDB uses Redis connection, no explicit close needed
            self._client = None
            self._graph = None
            logger.info("FalkorDB connection closed")


# Singleton instance
_falkordb_client: Optional[FalkorDBClient] = None


def get_falkordb_client(
    host: str = None,
    port: int = None,
    graph_name: str = "text2sql_knowledge"
) -> FalkorDBClient:
    """
    Get or create FalkorDB client singleton.
    
    Uses configuration from environment if not provided.
    """
    global _falkordb_client
    
    if _falkordb_client is None:
        import os
        
        host = host or os.getenv("FALKORDB_HOST", "localhost")
        port = port or int(os.getenv("FALKORDB_PORT", "6379"))
        username = os.getenv("FALKORDB_USERNAME")
        password = os.getenv("FALKORDB_PASSWORD")
        
        _falkordb_client = FalkorDBClient(
            host=host,
            port=port,
            username=username,
            password=password,
            graph_name=graph_name
        )
    
    return _falkordb_client

