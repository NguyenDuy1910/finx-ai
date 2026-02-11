from enum import Enum
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field
from graphiti_core.nodes import EntityNode


class NodeLabel(str, Enum):
    TABLE = "Table"
    COLUMN = "Column"
    BUSINESS_ENTITY = "BusinessEntity"
    QUERY_PATTERN = "QueryPattern"


class TableNode(BaseModel):
    name: str
    database: str
    description: str = ""
    partition_keys: List[str] = Field(default_factory=list)
    row_count: Optional[int] = None
    storage_format: str = ""
    location: str = ""

    def to_entity_node(self, group_id: str) -> EntityNode:
        return EntityNode(
            name=f"{self.database}.{self.name}",
            group_id=group_id,
            labels=[NodeLabel.TABLE],
            summary=self.description,
            attributes={
                "database": self.database,
                "table_name": self.name,
                "partition_keys": self.partition_keys,
                "row_count": self.row_count,
                "storage_format": self.storage_format,
                "location": self.location,
            },
        )

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "TableNode":
        attrs = node.attributes or {}
        db_table = node.name.split(".", 1)
        database = attrs.get("database", db_table[0] if len(db_table) > 1 else "")
        table_name = attrs.get("table_name", db_table[-1])
        return cls(
            name=table_name,
            database=database,
            description=node.summary or "",
            partition_keys=attrs.get("partition_keys", []),
            row_count=attrs.get("row_count"),
            storage_format=attrs.get("storage_format", ""),
            location=attrs.get("location", ""),
        )


class ColumnNode(BaseModel):
    name: str
    table_name: str
    database: str
    data_type: str = "string"
    description: str = ""
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_partition: bool = False
    is_nullable: bool = True
    sample_values: List[str] = Field(default_factory=list)

    def to_entity_node(self, group_id: str) -> EntityNode:
        return EntityNode(
            name=f"{self.database}.{self.table_name}.{self.name}",
            group_id=group_id,
            labels=[NodeLabel.COLUMN],
            summary=self.description,
            attributes={
                "database": self.database,
                "table_name": self.table_name,
                "column_name": self.name,
                "data_type": self.data_type,
                "is_primary_key": self.is_primary_key,
                "is_foreign_key": self.is_foreign_key,
                "is_partition": self.is_partition,
                "is_nullable": self.is_nullable,
                "sample_values": self.sample_values,
            },
        )

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "ColumnNode":
        attrs = node.attributes or {}
        parts = node.name.split(".")
        return cls(
            name=attrs.get("column_name", parts[-1] if parts else ""),
            table_name=attrs.get("table_name", parts[-2] if len(parts) > 1 else ""),
            database=attrs.get("database", parts[0] if len(parts) > 2 else ""),
            data_type=attrs.get("data_type", "string"),
            description=node.summary or "",
            is_primary_key=attrs.get("is_primary_key", False),
            is_foreign_key=attrs.get("is_foreign_key", False),
            is_partition=attrs.get("is_partition", False),
            is_nullable=attrs.get("is_nullable", True),
            sample_values=attrs.get("sample_values", []),
        )


class BusinessEntityNode(BaseModel):
    name: str
    domain: str = "business"
    description: str = ""
    synonyms: List[str] = Field(default_factory=list)
    mapped_tables: List[str] = Field(default_factory=list)

    def to_entity_node(self, group_id: str) -> EntityNode:
        return EntityNode(
            name=self.name,
            group_id=group_id,
            labels=[NodeLabel.BUSINESS_ENTITY],
            summary=self.description,
            attributes={
                "domain": self.domain,
                "synonyms": self.synonyms,
                "mapped_tables": self.mapped_tables,
            },
        )

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "BusinessEntityNode":
        attrs = node.attributes or {}
        return cls(
            name=node.name,
            domain=attrs.get("domain", "business"),
            description=node.summary or "",
            synonyms=attrs.get("synonyms", []),
            mapped_tables=attrs.get("mapped_tables", []),
        )


class QueryPatternNode(BaseModel):
    name: str
    intent: str
    pattern: str
    sql_template: str = ""
    frequency: int = 0
    success_rate: float = 0.0
    last_used: Optional[datetime] = None
    tables_involved: List[str] = Field(default_factory=list)

    def to_entity_node(self, group_id: str) -> EntityNode:
        return EntityNode(
            name=f"pattern_{self.intent}_{self.name}",
            group_id=group_id,
            labels=[NodeLabel.QUERY_PATTERN],
            summary=f"{self.intent}: {self.pattern}",
            attributes={
                "intent": self.intent,
                "pattern": self.pattern,
                "sql_template": self.sql_template,
                "frequency": self.frequency,
                "success_rate": self.success_rate,
                "last_used": self.last_used.isoformat() if self.last_used else None,
                "tables_involved": self.tables_involved,
            },
        )

    @classmethod
    def from_entity_node(cls, node: EntityNode) -> "QueryPatternNode":
        attrs = node.attributes or {}
        last_used_str = attrs.get("last_used")
        last_used = datetime.fromisoformat(last_used_str) if last_used_str else None
        return cls(
            name=node.name,
            intent=attrs.get("intent", ""),
            pattern=attrs.get("pattern", ""),
            sql_template=attrs.get("sql_template", ""),
            frequency=attrs.get("frequency", 0),
            success_rate=attrs.get("success_rate", 0.0),
            last_used=last_used,
            tables_involved=attrs.get("tables_involved", []),
        )

