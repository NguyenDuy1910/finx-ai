import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from .athena_reader import AthenaSchemaReader

logger = logging.getLogger(__name__)


@dataclass
class ColumnChange:
    name: str
    change_type: str
    old_type: Optional[str] = None
    new_type: Optional[str] = None


@dataclass
class TableChange:
    table_name: str
    database: str
    change_type: str
    new_columns: List[ColumnChange] = field(default_factory=list)
    removed_columns: List[ColumnChange] = field(default_factory=list)
    modified_columns: List[ColumnChange] = field(default_factory=list)
    schema_data: Optional[Dict[str, Any]] = None


@dataclass
class ChangeSet:
    new_tables: List[TableChange] = field(default_factory=list)
    removed_tables: List[TableChange] = field(default_factory=list)
    modified_tables: List[TableChange] = field(default_factory=list)
    unchanged_tables: List[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.new_tables or self.removed_tables or self.modified_tables)

    def summary(self) -> Dict[str, int]:
        total_new_cols = sum(len(t.new_columns) for t in self.modified_tables)
        total_removed_cols = sum(len(t.removed_columns) for t in self.modified_tables)
        total_modified_cols = sum(len(t.modified_columns) for t in self.modified_tables)
        return {
            "new_tables": len(self.new_tables),
            "removed_tables": len(self.removed_tables),
            "modified_tables": len(self.modified_tables),
            "unchanged_tables": len(self.unchanged_tables),
            "new_columns": total_new_cols,
            "removed_columns": total_removed_cols,
            "modified_columns": total_modified_cols,
        }


class SchemaChangeDetector:

    def __init__(
        self,
        database: str,
        region: str = "ap-southeast-1",
        profile: Optional[str] = None,
    ):
        self.database = database
        self.reader = AthenaSchemaReader(database, region, profile)
        self._snapshot: Dict[str, Dict[str, Any]] = {}

    def load_snapshot(self, existing_schemas: List[Dict[str, Any]]) -> None:
        self._snapshot = {s["name"]: s for s in existing_schemas}

    def detect_changes(
        self,
        tables: Optional[List[str]] = None,
    ) -> ChangeSet:
        if tables:
            current_schemas = [self.reader.get_table_schema(t) for t in tables]
        else:
            current_schemas = self.reader.get_all_schemas()

        current_map = {s["name"]: s for s in current_schemas}
        current_names = set(current_map.keys())
        existing_names = set(self._snapshot.keys())

        changeset = ChangeSet()

        for name in current_names - existing_names:
            changeset.new_tables.append(
                TableChange(
                    table_name=name,
                    database=self.database,
                    change_type="new",
                    schema_data=current_map[name],
                )
            )

        for name in existing_names - current_names:
            changeset.removed_tables.append(
                TableChange(
                    table_name=name,
                    database=self.database,
                    change_type="removed",
                    schema_data=self._snapshot[name],
                )
            )

        for name in current_names & existing_names:
            table_change = self._compare_table(
                self._snapshot[name], current_map[name]
            )
            if table_change:
                changeset.modified_tables.append(table_change)
            else:
                changeset.unchanged_tables.append(name)

        return changeset

    def _compare_table(
        self,
        existing: Dict[str, Any],
        current: Dict[str, Any],
    ) -> Optional[TableChange]:
        existing_cols = {c["name"]: c for c in existing.get("columns", [])}
        current_cols = {c["name"]: c for c in current.get("columns", [])}

        existing_col_names = set(existing_cols.keys())
        current_col_names = set(current_cols.keys())

        new_columns = []
        removed_columns = []
        modified_columns = []

        for col_name in current_col_names - existing_col_names:
            new_columns.append(
                ColumnChange(
                    name=col_name,
                    change_type="new",
                    new_type=current_cols[col_name].get("type"),
                )
            )

        for col_name in existing_col_names - current_col_names:
            removed_columns.append(
                ColumnChange(
                    name=col_name,
                    change_type="removed",
                    old_type=existing_cols[col_name].get("type"),
                )
            )

        for col_name in current_col_names & existing_col_names:
            old_col = existing_cols[col_name]
            new_col = current_cols[col_name]
            if old_col.get("type") != new_col.get("type"):
                modified_columns.append(
                    ColumnChange(
                        name=col_name,
                        change_type="modified",
                        old_type=old_col.get("type"),
                        new_type=new_col.get("type"),
                    )
                )

        if not new_columns and not removed_columns and not modified_columns:
            return None

        return TableChange(
            table_name=current["name"],
            database=self.database,
            change_type="modified",
            new_columns=new_columns,
            removed_columns=removed_columns,
            modified_columns=modified_columns,
            schema_data=current,
        )
