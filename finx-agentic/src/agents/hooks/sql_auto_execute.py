"""Post-hook: auto-extract SQL from SQL Generator Agent response, execute on Athena,
and inject results back into the response content.

This eliminates tool-call overhead — the agent just generates SQL in its text
response, and this hook handles execution automatically via boto3.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from agno.agent import Agent
    from agno.run.agent import RunOutput

logger = logging.getLogger(__name__)

# ── SQL extraction patterns ──────────────────────────────────────────
SQL_FENCED_BLOCK = re.compile(
    r"```sql\s*\n(.*?)\n\s*```", re.DOTALL | re.IGNORECASE
)
DESTRUCTIVE_PATTERN = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|ALTER|INSERT|UPDATE|CREATE|MERGE)\b",
    re.IGNORECASE,
)


class AthenaDirectExecutor:
    """Lightweight Athena executor — no Toolkit overhead, just boto3 calls."""

    def __init__(
        self,
        database: str,
        output_location: str,
        region_name: str = "ap-southeast-1",
    ):
        import boto3

        self.database = database
        self.output_location = output_location
        self.client = boto3.client("athena", region_name=region_name)

    def execute(
        self, sql: str, database: Optional[str] = None, timeout: int = 60
    ) -> Dict[str, Any]:
        """Execute SQL on Athena and return structured result dict."""
        db = database or self.database
        try:
            resp = self.client.start_query_execution(
                QueryString=sql,
                QueryExecutionContext={"Database": db},
                ResultConfiguration={"OutputLocation": self.output_location},
            )
            execution_id = resp["QueryExecutionId"]

            start = time.time()
            while time.time() - start < timeout:
                status = self.client.get_query_execution(
                    QueryExecutionId=execution_id
                )
                state = status["QueryExecution"]["Status"]["State"]

                if state == "SUCCEEDED":
                    return self._get_results(execution_id)

                if state in ("FAILED", "CANCELLED"):
                    reason = status["QueryExecution"]["Status"].get(
                        "StateChangeReason", ""
                    )
                    return {
                        "status": "error",
                        "error": f"Query {state}: {reason}",
                        "execution_id": execution_id,
                        "sql": sql,
                    }

                time.sleep(1)

            return {
                "status": "error",
                "error": f"Query timed out after {timeout}s",
                "execution_id": execution_id,
                "sql": sql,
            }

        except Exception as e:
            logger.error("Athena execution failed: %s", e)
            return {"status": "error", "error": str(e), "sql": sql}

    def validate(self, sql: str, database: Optional[str] = None) -> Dict[str, Any]:
        """Validate SQL syntax via EXPLAIN — fast, no data scan."""
        db = database or self.database
        try:
            resp = self.client.start_query_execution(
                QueryString=f"EXPLAIN {sql}",
                QueryExecutionContext={"Database": db},
                ResultConfiguration={"OutputLocation": self.output_location},
            )
            execution_id = resp["QueryExecutionId"]

            start = time.time()
            while time.time() - start < 30:
                status = self.client.get_query_execution(
                    QueryExecutionId=execution_id
                )
                state = status["QueryExecution"]["Status"]["State"]
                if state == "SUCCEEDED":
                    return {"valid": True, "message": "SQL syntax is valid"}
                if state in ("FAILED", "CANCELLED"):
                    reason = status["QueryExecution"]["Status"].get(
                        "StateChangeReason", ""
                    )
                    return {"valid": False, "error": reason}
                time.sleep(0.5)

            return {"valid": False, "error": "Validation timed out"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def _get_results(
        self, execution_id: str, max_results: int = 1000
    ) -> Dict[str, Any]:
        """Fetch query results from a completed execution."""
        try:
            resp = self.client.get_query_results(
                QueryExecutionId=execution_id, MaxResults=max_results
            )
            result_set = resp.get("ResultSet", {})
            columns = [
                col["Label"]
                for col in result_set.get("ResultSetMetadata", {}).get(
                    "ColumnInfo", []
                )
            ]
            data_rows = result_set.get("Rows", [])[1:]  # skip header row
            rows = []
            for row in data_rows:
                values = [d.get("VarCharValue", "") for d in row.get("Data", [])]
                rows.append(dict(zip(columns, values)))

            return {
                "status": "success",
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "execution_id": execution_id,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "execution_id": execution_id,
            }


def _extract_sql(text: str) -> str | None:
    """Extract the first SQL block from agent response text."""
    match = SQL_FENCED_BLOCK.search(text)
    if match:
        sql = match.group(1).strip()
        if sql:
            return sql
    return None


def create_sql_auto_execute_hook(executor: AthenaDirectExecutor):
    """Factory: returns a post-hook function bound to a specific Athena executor.

    The hook:
      1. Extracts ```sql``` blocks from the agent's response
      2. Rejects destructive statements
      3. Validates syntax via EXPLAIN
      4. If valid, executes the query
      5. Appends results to the response content
    """

    def sql_auto_execute_hook(run_output: "RunOutput", agent: "Agent") -> None:
        content = run_output.content
        if not content or not isinstance(content, str):
            return

        sql = _extract_sql(content)
        if not sql:
            return

        # Safety: reject destructive SQL
        if DESTRUCTIVE_PATTERN.search(sql):
            result_block = (
                "\n\n<athena_result status=\"rejected\">\n"
                "REJECTED — destructive SQL detected. Only SELECT statements are allowed.\n"
                "</athena_result>"
            )
            run_output.content = content + result_block
            return

        logger.info("sql_auto_execute_hook: validating SQL")

        # Step 1: Validate
        validation = executor.validate(sql)
        if not validation.get("valid", False):
            error_msg = validation.get("error", "Unknown validation error")
            result_block = (
                f"\n\n<athena_result status=\"validation_error\">\n"
                f"SQL validation failed: {error_msg}\n"
                f"</athena_result>"
            )
            run_output.content = content + result_block
            return

        logger.info("sql_auto_execute_hook: SQL valid, executing")

        # Step 2: Execute
        result = executor.execute(sql)

        if result.get("status") == "success":
            result_json = json.dumps(
                {
                    "columns": result["columns"],
                    "rows": result["rows"],
                    "row_count": result["row_count"],
                    "execution_id": result.get("execution_id", ""),
                },
                default=str,
                ensure_ascii=False,
            )
            result_block = (
                f"\n\n<athena_result status=\"success\" "
                f"row_count=\"{result['row_count']}\" "
                f"execution_id=\"{result.get('execution_id', '')}\">\n"
                f"{result_json}\n"
                f"</athena_result>"
            )
        else:
            error_msg = result.get("error", "Unknown error")
            result_block = (
                f"\n\n<athena_result status=\"error\">\n"
                f"Execution failed: {error_msg}\n"
                f"</athena_result>"
            )

        run_output.content = content + result_block
        logger.info(
            "sql_auto_execute_hook: done, status=%s",
            result.get("status", "unknown"),
        )

    return sql_auto_execute_hook
