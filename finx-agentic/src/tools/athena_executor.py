import json
import time
import logging
from typing import Any, Dict, List, Optional

from agno.tools import Toolkit

logger = logging.getLogger(__name__)

try:
    import boto3
except ImportError:
    raise ImportError("boto3 is required for AthenaExecutorTools")


class AthenaExecutorTools(Toolkit):

    def __init__(
        self,
        database: str,
        output_location: str,
        region_name: str = "ap-southeast-1",
        **kwargs,
    ):
        self.database = database
        self.output_location = output_location
        self.athena_client = boto3.client("athena", region_name=region_name)

        tools: List[Any] = [
            self.execute_sql,
            self.validate_sql_syntax,
        ]
        super().__init__(name="athena_executor_tools", tools=tools, **kwargs)

    def execute_sql(self, sql: str, database: Optional[str] = None, timeout: int = 60) -> str:
        db = database or self.database
        try:
            response = self.athena_client.start_query_execution(
                QueryString=sql,
                QueryExecutionContext={"Database": db},
                ResultConfiguration={"OutputLocation": self.output_location},
            )
            execution_id = response["QueryExecutionId"]

            start = time.time()
            while time.time() - start < timeout:
                status = self.athena_client.get_query_execution(QueryExecutionId=execution_id)
                state = status["QueryExecution"]["Status"]["State"]
                if state == "SUCCEEDED":
                    return self._get_results(execution_id)
                if state in ("FAILED", "CANCELLED"):
                    reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
                    return json.dumps({"error": f"Query {state}: {reason}", "execution_id": execution_id})
                time.sleep(1)

            return json.dumps({"error": "Query timed out", "execution_id": execution_id})
        except Exception as e:
            logger.error(f"Athena execution failed: {e}")
            return json.dumps({"error": str(e)})

    def validate_sql_syntax(self, sql: str, database: Optional[str] = None) -> str:
        db = database or self.database
        explain_sql = f"EXPLAIN {sql}"
        try:
            response = self.athena_client.start_query_execution(
                QueryString=explain_sql,
                QueryExecutionContext={"Database": db},
                ResultConfiguration={"OutputLocation": self.output_location},
            )
            execution_id = response["QueryExecutionId"]

            start = time.time()
            while time.time() - start < 30:
                status = self.athena_client.get_query_execution(QueryExecutionId=execution_id)
                state = status["QueryExecution"]["Status"]["State"]
                if state == "SUCCEEDED":
                    return json.dumps({"valid": True, "message": "SQL syntax is valid"})
                if state in ("FAILED", "CANCELLED"):
                    reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
                    return json.dumps({"valid": False, "error": reason})
                time.sleep(0.5)

            return json.dumps({"valid": False, "error": "Validation timed out"})
        except Exception as e:
            return json.dumps({"valid": False, "error": str(e)})

    def _get_results(self, execution_id: str, max_results: int = 1000) -> str:
        try:
            response = self.athena_client.get_query_results(
                QueryExecutionId=execution_id, MaxResults=max_results
            )
            result_set = response.get("ResultSet", {})
            columns = [col["Label"] for col in result_set.get("ResultSetMetadata", {}).get("ColumnInfo", [])]
            data_rows = result_set.get("Rows", [])[1:]
            rows = []
            for row in data_rows:
                values = [d.get("VarCharValue", "") for d in row.get("Data", [])]
                rows.append(dict(zip(columns, values)))
            return json.dumps({
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "execution_id": execution_id,
            }, default=str)
        except Exception as e:
            return json.dumps({"error": str(e), "execution_id": execution_id})

