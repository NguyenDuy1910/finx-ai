import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from .domain_generator import DomainGenerator
from .schema_change_detector import SchemaChangeDetector, ChangeSet, TableChange
from .graph_updater import GraphUpdater

logger = logging.getLogger(__name__)

DEFAULT_COST_LIMIT_USD = 1.0
DEFAULT_MAX_CONCURRENCY = 5


class CostLimitExceeded(Exception):

    def __init__(self, current_cost: float, limit: float):
        self.current_cost = current_cost
        self.limit = limit
        super().__init__(
            f"LLM cost ${current_cost:.6f} exceeded limit ${limit:.2f}"
        )


class IncrementalSchemaSync:

    def __init__(
        self,
        database: str,
        schema_dir: str,
        graph_updater: GraphUpdater,
        region: str = "ap-southeast-1",
        profile: Optional[str] = None,
        cost_limit_usd: float = DEFAULT_COST_LIMIT_USD,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ):
        self.database = database
        self.schema_dir = Path(schema_dir)
        self.generator = DomainGenerator()
        self.detector = SchemaChangeDetector(database, region, profile)
        self.updater = graph_updater
        self.cost_limit_usd = cost_limit_usd
        self.max_concurrency = max_concurrency
        self._cost_exceeded = False

    async def sync(self, tables: Optional[List[str]] = None) -> Dict[str, Any]:
        snapshot = self._load_local_snapshot()
        self.detector.load_snapshot(snapshot)

        changeset = self.detector.detect_changes(tables)

        logger.info(f"Change summary: {changeset.summary()}")

        if not changeset.has_changes:
            logger.info("No schema changes detected")
            return {"status": "no_changes", "summary": changeset.summary()}

        stats = {
            "new_tables": 0,
            "new_columns": 0,
            "removed_columns": 0,
            "modified_columns": 0,
            "skipped_removed_tables": 0,
            "stopped_by_cost_limit": False,
        }

        self._cost_exceeded = False
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _process_new_table(tc: TableChange) -> bool:
            if self._cost_exceeded:
                return False
            async with semaphore:
                if self._cost_exceeded:
                    return False
                cost_before = self.generator.cost_tracker.total_cost_usd
                await self._handle_new_table(tc)
                self._log_table_cost(tc.table_name, "new", cost_before)
                if self.generator.cost_tracker.total_cost_usd >= self.cost_limit_usd:
                    self._cost_exceeded = True
                return True

        async def _process_modified_table(tc: TableChange) -> Dict[str, int]:
            if self._cost_exceeded:
                return {"new_columns": 0, "removed_columns": 0, "modified_columns": 0}
            async with semaphore:
                if self._cost_exceeded:
                    return {"new_columns": 0, "removed_columns": 0, "modified_columns": 0}
                cost_before = self.generator.cost_tracker.total_cost_usd
                result = await self._handle_modified_table(tc)
                self._log_table_cost(tc.table_name, "modified", cost_before)
                if self.generator.cost_tracker.total_cost_usd >= self.cost_limit_usd:
                    self._cost_exceeded = True
                return result

        if changeset.new_tables:
            logger.info(f"Processing {len(changeset.new_tables)} new tables (concurrency={self.max_concurrency})")
            tasks = [_process_new_table(tc) for tc in changeset.new_tables]
            results = await asyncio.gather(*tasks)
            stats["new_tables"] = sum(1 for r in results if r)

        for table_change in changeset.removed_tables:
            logger.info(f"Skipped removed table: {table_change.table_name}")
            stats["skipped_removed_tables"] += 1

        if changeset.modified_tables and not self._cost_exceeded:
            logger.info(f"Processing {len(changeset.modified_tables)} modified tables (concurrency={self.max_concurrency})")
            tasks = [_process_modified_table(tc) for tc in changeset.modified_tables]
            results = await asyncio.gather(*tasks)
            for r in results:
                stats["new_columns"] += r.get("new_columns", 0)
                stats["removed_columns"] += r.get("removed_columns", 0)
                stats["modified_columns"] += r.get("modified_columns", 0)

        if self._cost_exceeded:
            logger.warning(
                f"Stopped: LLM cost ${self.generator.cost_tracker.total_cost_usd:.6f} "
                f"exceeded limit ${self.cost_limit_usd:.2f}"
            )
            stats["stopped_by_cost_limit"] = True

        self._update_index()

        return {
            "status": "updated",
            "summary": changeset.summary(),
            "stats": stats,
            "llm_cost": self.generator.cost_tracker.to_dict(),
        }

    def _load_local_snapshot(self) -> List[Dict[str, Any]]:
        schemas = []
        if not self.schema_dir.exists():
            return schemas
        for json_file in self.schema_dir.glob("*.json"):
            if json_file.name.startswith("_"):
                continue
            with open(json_file, "r") as f:
                schemas.append(json.load(f))
        return schemas

    def _log_table_cost(self, table_name: str, change_type: str, cost_before: float) -> None:
        cost_after = self.generator.cost_tracker.total_cost_usd
        table_cost = cost_after - cost_before
        logger.info(
            f"[cost] {table_name} ({change_type}): "
            f"${table_cost:.6f} | cumulative: ${cost_after:.6f} / ${self.cost_limit_usd:.2f}"
        )

    def _check_cost_limit(self) -> None:
        if self.generator.cost_tracker.total_cost_usd >= self.cost_limit_usd:
            self._cost_exceeded = True

    async def _handle_new_table(self, table_change: TableChange) -> None:
        logger.info(f"New table: {table_change.table_name}")
        schema = table_change.schema_data
        enriched = await self.generator.generate_domain_terms(schema)
        self._save_schema(table_change.table_name, enriched)
        await self.updater.add_table(enriched)

    async def _handle_modified_table(self, table_change: TableChange) -> Dict[str, int]:
        logger.info(f"Modified table: {table_change.table_name}")
        result = {"new_columns": 0, "removed_columns": 0, "modified_columns": 0}

        existing_schema = self._load_schema(table_change.table_name)

        if table_change.new_columns:
            new_col_names = [c.name for c in table_change.new_columns]
            logger.info(f"  New columns: {new_col_names}")

            updated = await self.generator.generate_column_terms(
                table_change.schema_data,
                new_col_names,
                existing_schema,
            )

            new_col_data = [c for c in updated.get("columns", []) if c["name"] in new_col_names]
            if not new_col_data:
                new_col_data = [
                    {"name": c.name, "type": c.new_type or "string", "description": ""}
                    for c in table_change.new_columns
                ]

            existing_col_count = len(existing_schema.get("columns", []))
            await self.updater.add_columns(
                table_change.table_name,
                table_change.database,
                new_col_data,
                start_ordinal=existing_col_count,
            )
            result["new_columns"] = len(new_col_data)

            if updated and updated.get("columns"):
                self._save_schema(table_change.table_name, updated)

        if table_change.removed_columns:
            removed_col_names = [c.name for c in table_change.removed_columns]
            logger.info(f"  Removed columns: {removed_col_names}")
            await self.updater.remove_columns(
                table_change.table_name,
                table_change.database,
                removed_col_names,
            )
            result["removed_columns"] = len(removed_col_names)
            self._remove_columns_from_schema(table_change.table_name, removed_col_names)

        if table_change.modified_columns:
            for col_change in table_change.modified_columns:
                logger.info(f"  Modified column: {col_change.name} ({col_change.old_type} -> {col_change.new_type})")
                await self.updater.update_column_type(
                    table_change.table_name,
                    table_change.database,
                    col_change.name,
                    col_change.new_type,
                )
            result["modified_columns"] = len(table_change.modified_columns)
            self._update_column_types_in_schema(table_change.table_name, table_change.modified_columns)

        return result

    def _save_schema(self, table_name: str, schema_data: Dict[str, Any]) -> None:
        self.schema_dir.mkdir(parents=True, exist_ok=True)
        output_file = self.schema_dir / f"{table_name}.json"
        with open(output_file, "w") as f:
            json.dump(schema_data, f, indent=2)

    def _load_schema(self, table_name: str) -> Optional[Dict[str, Any]]:
        schema_file = self.schema_dir / f"{table_name}.json"
        if not schema_file.exists():
            return None
        with open(schema_file, "r") as f:
            return json.load(f)

    def _remove_columns_from_schema(self, table_name: str, column_names: List[str]) -> None:
        schema = self._load_schema(table_name)
        if not schema:
            return
        schema["columns"] = [c for c in schema["columns"] if c["name"] not in column_names]
        self._save_schema(table_name, schema)

    def _update_column_types_in_schema(self, table_name: str, column_changes: list) -> None:
        schema = self._load_schema(table_name)
        if not schema:
            return
        type_map = {c.name: c.new_type for c in column_changes}
        for col in schema["columns"]:
            if col["name"] in type_map:
                col["type"] = type_map[col["name"]]
        self._save_schema(table_name, schema)

    def _update_index(self) -> None:
        if not self.schema_dir.exists():
            return
        json_files = [f for f in self.schema_dir.glob("*.json") if not f.name.startswith("_")]
        index = {
            "database": self.database,
            "tables": [f.stem for f in json_files],
            "count": len(json_files),
        }
        index_file = self.schema_dir / "_index.json"
        with open(index_file, "w") as f:
            json.dump(index, f, indent=2)
