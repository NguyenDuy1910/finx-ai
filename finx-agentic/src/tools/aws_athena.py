from typing import Any, Dict, List, Optional
import time
import json
from textwrap import dedent
from agno.tools import Toolkit
from agno.utils.log import logger

try:
    import boto3
except ImportError:
    raise ImportError("boto3 is required for AWSAthenaTools. Please install it using `pip install boto3`.")


class AWSAthenaTools(Toolkit):
    DEFAULT_INSTRUCTIONS = dedent("""
        You are an expert at querying AWS Athena.
        Your goal is to answer user questions by running SQL queries against Athena tables.

        Guidelines:
        1. **Explore Schema First**: If you don't know the table structure, use `list_tables` and `describe_table` to understand the columns and data types.
        2. **Write Standard SQL**: Athena uses Presto/Trino SQL syntax. Ensure your queries are compatible.
        3. **Limit Results**: When exploring data, use `LIMIT` to avoid fetching too much data.
        4. **Handle Errors**: If a query fails, read the error message carefully and adjust your query.
        5. **Database Context**: Always specify the `database` name when running queries or listing tables.
        6. **Output**: When you get results, summarize them typically or answer the specific question asked.
    """)

    FEW_SHOT_EXAMPLES = dedent("""
        # Example: List tables in 'default' database
        # tool.list_tables(database_name="default")

        # Example: Count rows in a table
        # tool.run_query(query_string="SELECT COUNT(*) FROM my_table", database="default")
    """)

    def __init__(
        self,
        region_name: str = "us-east-1",
        enable_list_tables: bool = True,
        enable_describe_table: bool = True,
        enable_run_query: bool = True,
        enable_get_query_results: bool = True,
        enable_get_query_execution: bool = True,
        tables: Optional[Dict[str, Any]] = None,
        schema: Optional[str] = None,
        instructions: Optional[str] = None,
        add_few_shot: bool = False,
        few_shot_examples: Optional[str] = None,
        **kwargs,
    ):
        if instructions is None:
            self.instructions = "<reasoning_instructions>\n" + self.DEFAULT_INSTRUCTIONS
            if add_few_shot:
                if few_shot_examples is not None:
                    self.instructions += "\n" + few_shot_examples
                else:
                    self.instructions += "\n" + self.FEW_SHOT_EXAMPLES
            self.instructions += "\n</reasoning_instructions>\n"
        else:
            self.instructions = instructions

        self.client = boto3.client("athena", region_name=region_name)   
        self.schema = schema
        self.tables: Optional[Dict[str, Any]] = tables
        tools: List[Any] = []
        if enable_list_tables or all:
            tools.append(self.list_tables)
        if enable_describe_table or all:
            tools.append(self.describe_table)
        if enable_run_query or all:
            tools.append(self.run_query)
        if enable_get_query_results or all:
            tools.append(self.get_query_results)    
        if enable_get_query_execution or all:
            tools.append(self.get_query_execution)

        super().__init__(name="aws_athena_tools", tools=tools, **kwargs)

    def start_query_execution(
        self, query_string: str, database: str, output_location: Optional[str] = None
    ) -> str:
        """
        Submits a query to Athena for execution.

        Args:
            query_string (str): The SQL query statements to be executed.
            database (str): The name of the database.
            output_location (Optional[str]): The location in Amazon S3 where your query results are stored.

        Returns:
            str: The unique identifier for the query execution.
        """
        query_execution_context = {"Database": database}
        result_configuration = {}
        if output_location:
            result_configuration["OutputLocation"] = output_location

        try:
            response = self.client.start_query_execution(
                QueryString=query_string,
                QueryExecutionContext=query_execution_context,
                ResultConfiguration=result_configuration,
            )
            return response["QueryExecutionId"]
        except Exception as e:
            logger.error(f"Error starting query execution: {e}")
            raise

    def get_query_execution(self, query_execution_id: str) -> str:
        """
        Returns the details of a single query execution.

        Args:
            query_execution_id (str): The unique identifier for the query execution.

        Returns:
            str: JSON string containing the query execution details.
        """
        try:
            response = self.client.get_query_execution(QueryExecutionId=query_execution_id)
            return json.dumps(response.get("QueryExecution", {}), default=str)
        except Exception as e:
            logger.error(f"Error getting query execution details: {e}")
            return json.dumps({"error": str(e)})

    def get_query_results(self, query_execution_id: str, max_results: int = 1000) -> str:
        """
        Streams the results of a single query execution from Athena.

        Args:
            query_execution_id (str): The unique identifier for the query execution.
            max_results (int): The maximum number of results (rows) to return.

        Returns:
            str: JSON string containing the query results.
        """
        try:
            response = self.client.get_query_results(
                QueryExecutionId=query_execution_id, MaxResults=max_results
            )
            # Process results to make them more readable (skipping complex type handling for brevity)
            # This returns the raw ResultSet from boto3
            return json.dumps(response.get("ResultSet", {}), default=str)
        except Exception as e:
            logger.error(f"Error getting query results: {e}")
            return json.dumps({"error": str(e)})

    def run_query(
        self,
        query_string: str,
        database: str,
        output_location: Optional[str] = None,
        wait_timeout: int = 60,
    ) -> str:
        """
        Runs a query on Athena and waits for the results.

        Args:
            query_string (str): The SQL query statements to be executed.
            database (str): The name of the database.
            output_location (Optional[str]): The location in Amazon S3 where your query results are stored.
            wait_timeout (int): Maximum time in seconds to wait for the query to complete.

        Returns:
            str: JSON string containing the query results or error message.
        """
        try:
            query_execution_id = self.start_query_execution(
                query_string=query_string,
                database=database,
                output_location=output_location
            )
            
            # Wait for query to complete
            start_time = time.time()
            while time.time() - start_time < wait_timeout:
                execution_status = json.loads(self.get_query_execution(query_execution_id))
                state = execution_status.get("Status", {}).get("State")
                
                if state in ["SUCCEEDED"]:
                    return self.get_query_results(query_execution_id)
                elif state in ["FAILED", "CANCELLED"]:
                    reason = execution_status.get("Status", {}).get("StateChangeReason")
                    return json.dumps({"error": f"Query {state}: {reason}"})
                
                time.sleep(1)  # Poll every second
            
            return json.dumps({"error": "Query timed out waiting for results"})
            
        except Exception as e:
            return json.dumps({"error": str(e)})

    def list_databases(self, catalog_name: str = "AwsDataCatalog") -> str:
        """
        Lists the databases in the specified data catalog.

        Args:
            catalog_name (str): The name of the data catalog.

        Returns:
            str: JSON string containing the list of databases.
        """
        try:
            response = self.client.list_databases(CatalogName=catalog_name)
            return json.dumps(response.get("DatabaseList", []), default=str)
        except Exception as e:
            logger.error(f"Error listing databases: {e}")
            return json.dumps({"error": str(e)})

    def list_tables(self, database_name: str, catalog_name: str = "AwsDataCatalog") -> str:
        """
        Lists the tables in the specified database.

        Args:
            database_name (str): The name of the database.
            catalog_name (str): The name of the data catalog.

        Returns:
            str: JSON string containing the list of tables.
        """
        try:
            response = self.client.list_table_metadata(
                CatalogName=catalog_name, DatabaseName=database_name
            )
            return json.dumps(response.get("TableMetadataList", []), default=str)
        except Exception as e:
            logger.error(f"Error listing tables: {e}")
            return json.dumps({"error": str(e)})

    def get_table_metadata(
        self, database_name: str, table_name: str, catalog_name: str = "AwsDataCatalog"
    ) -> str:
        """
        Returns the metadata for a single table.

        Args:
            database_name (str): The name of the database.
            table_name (str): The name of the table.
            catalog_name (str): The name of the data catalog.

        Returns:
            str: JSON string containing the table metadata.
        """
        try:
            response = self.client.get_table_metadata(
                CatalogName=catalog_name, DatabaseName=database_name, TableName=table_name
            )
            return json.dumps(response.get("TableMetadata", {}), default=str)
        except Exception as e:
            logger.error(f"Error getting table metadata: {e}")
            return json.dumps({"error": str(e)})

    def describe_table(
        self, database_name: str, table_name: str, catalog_name: str = "AwsDataCatalog"
    ) -> str:
        """
        Describes the schema of a table by showing its columns and data types.
        This is a user-friendly alias for get_table_metadata.

        Args:
            database_name (str): The name of the database.
            table_name (str): The name of the table.
            catalog_name (str): The name of the data catalog.

        Returns:
            str: A formatted string showing table schema (columns and types).
        """
        try:
            metadata = json.loads(
                self.get_table_metadata(database_name, table_name, catalog_name)
            )
            
            if "error" in metadata:
                return json.dumps(metadata)
            
            # Format the output nicely
            table_info = f"Table: {metadata.get('Name', table_name)}\n"
            table_info += f"Database: {database_name}\n"
            table_info += f"Table Type: {metadata.get('TableType', 'N/A')}\n"
            
            columns = metadata.get("Columns", [])
            if columns:
                table_info += "\nColumns:\n"
                table_info += "-" * 60 + "\n"
                for col in columns:
                    col_name = col.get("Name", "unknown")
                    col_type = col.get("Type", "unknown")
                    col_comment = col.get("Comment", "")
                    table_info += f"  {col_name:<30} {col_type:<20}"
                    if col_comment:
                        table_info += f" -- {col_comment}"
                    table_info += "\n"
            
            partitions = metadata.get("PartitionKeys", [])
            if partitions:
                table_info += "\nPartition Keys:\n"
                table_info += "-" * 60 + "\n"
                for part in partitions:
                    part_name = part.get("Name", "unknown")
                    part_type = part.get("Type", "unknown")
                    table_info += f"  {part_name:<30} {part_type:<20}\n"
            
            return table_info
            
        except Exception as e:
            logger.error(f"Error describing table: {e}")
            return json.dumps({"error": str(e)})


