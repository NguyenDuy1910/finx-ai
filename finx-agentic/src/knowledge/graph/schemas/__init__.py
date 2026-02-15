"""Base classes for graph node and edge models – eliminates boilerplate."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict

from pydantic import BaseModel
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge


class BaseNode(BaseModel, ABC):
    """Abstract base for every graph-node Pydantic model.

    Subclasses only need to implement three tiny methods:
    ``_label``, ``_node_name``, and ``_build_attributes``.
    The heavy ``to_entity_node`` / generic helpers are provided for free.
    """

    name: str
    description: str = ""

    # -- subclass hooks --------------------------------------------------

    @abstractmethod
    def _label(self) -> str:
        """Return the graph label, e.g. ``NodeLabel.TABLE``."""
        ...

    def _node_name(self) -> str:
        """Override if the node name differs from ``self.name``."""
        return self.name

    def _summary(self) -> str:
        """Override to customise the summary stored on the node."""
        return self.description

    @abstractmethod
    def _build_attributes(self) -> Dict[str, Any]:
        """Return the dict persisted as ``node.attributes``."""
        ...

    # -- public API ------------------------------------------------------

    def to_entity_node(self, group_id: str) -> EntityNode:
        return EntityNode(
            name=self._node_name(),
            group_id=group_id,
            labels=[self._label()],
            summary=self._summary(),
            attributes=self._build_attributes(),
        )


class BaseEdge(BaseModel, ABC):
    """Abstract base for every graph-edge Pydantic model.

    Subclasses only need to implement ``_edge_type``, ``_fact``, and
    ``_build_attributes``.  The repetitive ``to_entity_edge`` method is
    provided here once.
    """

    # -- subclass hooks --------------------------------------------------

    @abstractmethod
    def _edge_type(self) -> str:
        """Return the edge-type enum value, e.g. ``EdgeType.HAS_COLUMN``."""
        ...

    @abstractmethod
    def _fact(self) -> str:
        """Human-readable sentence describing this relationship."""
        ...

    @abstractmethod
    def _build_attributes(self) -> Dict[str, Any]:
        """Return the dict persisted as ``edge.attributes``."""
        ...

    # -- public API ------------------------------------------------------

    def to_entity_edge(
        self,
        source_node_uuid: str,
        target_node_uuid: str,
        group_id: str,
    ) -> EntityEdge:
        return EntityEdge(
            source_node_uuid=source_node_uuid,
            target_node_uuid=target_node_uuid,
            group_id=group_id,
            created_at=datetime.now(timezone.utc),
            name=self._edge_type(),
            fact=self._fact(),
            attributes={"edge_type": self._edge_type(), **self._build_attributes()},
        )
