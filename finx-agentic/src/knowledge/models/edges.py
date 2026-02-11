from enum import Enum
from datetime import datetime, timezone

from pydantic import BaseModel
from graphiti_core.edges import EntityEdge


class EdgeType(str, Enum):
    HAS_COLUMN = "HAS_COLUMN"
    JOIN = "JOIN"
    ENTITY_MAPPING = "ENTITY_MAPPING"
    QUERY_USES_TABLE = "QUERY_USES_TABLE"
    SYNONYM = "SYNONYM"
    FOREIGN_KEY = "FOREIGN_KEY"


class HasColumnEdge(BaseModel):
    table_name: str
    database: str
    column_name: str
    ordinal_position: int = 0

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
            name=EdgeType.HAS_COLUMN,
            fact=f"Table {self.database}.{self.table_name} has column {self.column_name}",
            attributes={
                "edge_type": EdgeType.HAS_COLUMN,
                "table_name": self.table_name,
                "database": self.database,
                "column_name": self.column_name,
                "ordinal_position": self.ordinal_position,
            },
        )

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "HasColumnEdge":
        attrs = edge.attributes or {}
        return cls(
            table_name=attrs.get("table_name", ""),
            database=attrs.get("database", ""),
            column_name=attrs.get("column_name", ""),
            ordinal_position=attrs.get("ordinal_position", 0),
        )


class JoinEdge(BaseModel):
    source_table: str
    target_table: str
    database: str
    join_type: str = "INNER"
    source_column: str = ""
    target_column: str = ""
    join_condition: str = ""
    discovered_from: str = "manual"
    usage_count: int = 0

    def to_entity_edge(
        self,
        source_node_uuid: str,
        target_node_uuid: str,
        group_id: str,
    ) -> EntityEdge:
        condition = self.join_condition or f"{self.source_table}.{self.source_column} = {self.target_table}.{self.target_column}"
        return EntityEdge(
            source_node_uuid=source_node_uuid,
            target_node_uuid=target_node_uuid,
            group_id=group_id,
            created_at=datetime.now(timezone.utc),
            name=EdgeType.JOIN,
            fact=f"{self.source_table} joins {self.target_table} on {condition}",
            attributes={
                "edge_type": EdgeType.JOIN,
                "source_table": self.source_table,
                "target_table": self.target_table,
                "database": self.database,
                "join_type": self.join_type,
                "source_column": self.source_column,
                "target_column": self.target_column,
                "join_condition": condition,
                "discovered_from": self.discovered_from,
                "usage_count": self.usage_count,
            },
        )

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "JoinEdge":
        attrs = edge.attributes or {}
        return cls(
            source_table=attrs.get("source_table", ""),
            target_table=attrs.get("target_table", ""),
            database=attrs.get("database", ""),
            join_type=attrs.get("join_type", "INNER"),
            source_column=attrs.get("source_column", ""),
            target_column=attrs.get("target_column", ""),
            join_condition=attrs.get("join_condition", ""),
            discovered_from=attrs.get("discovered_from", "manual"),
            usage_count=attrs.get("usage_count", 0),
        )


class EntityMappingEdge(BaseModel):
    entity_name: str
    table_name: str
    database: str
    confidence: float = 1.0
    mapping_type: str = "direct"

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
            name=EdgeType.ENTITY_MAPPING,
            fact=f"Entity '{self.entity_name}' maps to table {self.database}.{self.table_name}",
            attributes={
                "edge_type": EdgeType.ENTITY_MAPPING,
                "entity_name": self.entity_name,
                "table_name": self.table_name,
                "database": self.database,
                "confidence": self.confidence,
                "mapping_type": self.mapping_type,
            },
        )

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "EntityMappingEdge":
        attrs = edge.attributes or {}
        return cls(
            entity_name=attrs.get("entity_name", ""),
            table_name=attrs.get("table_name", ""),
            database=attrs.get("database", ""),
            confidence=attrs.get("confidence", 1.0),
            mapping_type=attrs.get("mapping_type", "direct"),
        )


class QueryPatternEdge(BaseModel):
    pattern_name: str
    table_name: str
    database: str
    role: str = "source"
    frequency: int = 0

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
            name=EdgeType.QUERY_USES_TABLE,
            fact=f"Query pattern '{self.pattern_name}' uses table {self.database}.{self.table_name} as {self.role}",
            attributes={
                "edge_type": EdgeType.QUERY_USES_TABLE,
                "pattern_name": self.pattern_name,
                "table_name": self.table_name,
                "database": self.database,
                "role": self.role,
                "frequency": self.frequency,
            },
        )

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "QueryPatternEdge":
        attrs = edge.attributes or {}
        return cls(
            pattern_name=attrs.get("pattern_name", ""),
            table_name=attrs.get("table_name", ""),
            database=attrs.get("database", ""),
            role=attrs.get("role", "source"),
            frequency=attrs.get("frequency", 0),
        )


class ForeignKeyEdge(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    database: str
    constraint_name: str = ""

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
            name=EdgeType.FOREIGN_KEY,
            fact=f"{self.source_table}.{self.source_column} references {self.target_table}.{self.target_column}",
            attributes={
                "edge_type": EdgeType.FOREIGN_KEY,
                "source_table": self.source_table,
                "source_column": self.source_column,
                "target_table": self.target_table,
                "target_column": self.target_column,
                "database": self.database,
                "constraint_name": self.constraint_name,
            },
        )

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "ForeignKeyEdge":
        attrs = edge.attributes or {}
        return cls(
            source_table=attrs.get("source_table", ""),
            source_column=attrs.get("source_column", ""),
            target_table=attrs.get("target_table", ""),
            target_column=attrs.get("target_column", ""),
            database=attrs.get("database", ""),
            constraint_name=attrs.get("constraint_name", ""),
        )


class SynonymEdge(BaseModel):
    term: str
    synonym: str
    confidence: float = 1.0

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
            name=EdgeType.SYNONYM,
            fact=f"'{self.term}' is a synonym for '{self.synonym}'",
            attributes={
                "edge_type": EdgeType.SYNONYM,
                "term": self.term,
                "synonym": self.synonym,
                "confidence": self.confidence,
            },
        )

    @classmethod
    def from_entity_edge(cls, edge: EntityEdge) -> "SynonymEdge":
        attrs = edge.attributes or {}
        return cls(
            term=attrs.get("term", ""),
            synonym=attrs.get("synonym", ""),
            confidence=attrs.get("confidence", 1.0),
        )

