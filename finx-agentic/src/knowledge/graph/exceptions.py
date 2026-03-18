"""Graph module exceptions."""
from __future__ import annotations


class GraphError(Exception):
    """Base exception for all graph operations."""


class GraphConnectionError(GraphError):
    """Failed to connect to FalkorDB."""

    def __init__(self, host: str, port: int, cause: Exception | None = None):
        self.host = host
        self.port = port
        self.cause = cause
        super().__init__(f"Cannot connect to FalkorDB at {host}:{port}: {cause}")


class NodeNotFoundError(GraphError):
    """Requested node does not exist in the graph."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        super().__init__(f"Node not found: {node_id!r}")


class EdgeNotFoundError(GraphError):
    """Requested edge does not exist in the graph."""

    def __init__(self, src: str, tgt: str, edge_type: str = ""):
        self.src = src
        self.tgt = tgt
        self.edge_type = edge_type
        label = f"{src!r}-[{edge_type}]->{tgt!r}" if edge_type else f"{src!r}->{tgt!r}"
        super().__init__(f"Edge not found: {label}")


class SchemaSetupError(GraphError):
    """Failed to create indexes or constraints."""
