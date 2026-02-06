from typing import Any, Dict, List
import boto3
from ..core.provider import BaseMCPProvider
from ..core.types import MCPResponse


class AthenaProvider(BaseMCPProvider):
    def _setup(self) -> None:
        self.region = self.config.settings.get("region", "us-east-1")
        self.database = self.config.settings.get("database", "default")
        self.output_location = self.config.settings.get("output_location")
        
        # AWS profile (optional) - if specified, use that profile from ~/.aws/credentials
        aws_profile = self.config.settings.get("aws_profile")
        
        # Create boto3 session with profile if specified, otherwise use default credential chain
        if aws_profile:
            session = boto3.Session(profile_name=aws_profile, region_name=self.region)
            self.client = session.client("athena")
        else:
            self.client = boto3.client("athena", region_name=self.region)
        
        @self.mcp.tool()
        def execute_query(query: str, database: str = None) -> Dict[str, Any]:
            db = database or self.database
            response = self.client.start_query_execution(
                QueryString=query,
                QueryExecutionContext={"Database": db},
                ResultConfiguration={"OutputLocation": self.output_location}
            )
            return {"execution_id": response["QueryExecutionId"]}
        
        @self.mcp.tool()
        def get_query_status(execution_id: str) -> Dict[str, Any]:
            response = self.client.get_query_execution(QueryExecutionId=execution_id)
            return {
                "state": response["QueryExecution"]["Status"]["State"],
                "submission_time": str(response["QueryExecution"]["Status"]["SubmissionDateTime"]),
                "completion_time": str(response["QueryExecution"]["Status"].get("CompletionDateTime", "")),
            }
        
        @self.mcp.tool()
        def get_query_results(execution_id: str, max_results: int = 100) -> Dict[str, Any]:
            response = self.client.get_query_results(
                QueryExecutionId=execution_id,
                MaxResults=max_results
            )
            
            columns = [col["Name"] for col in response["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
            rows = []
            for row in response["ResultSet"]["Rows"][1:]:
                rows.append([field.get("VarCharValue", "") for field in row["Data"]])
            
            return {"columns": columns, "rows": rows}
        
        @self.mcp.tool()
        def list_databases() -> List[str]:
            response = self.client.list_databases(CatalogName="AwsDataCatalog")
            return [db["Name"] for db in response["DatabaseList"]]
        
        @self.mcp.tool()
        def list_tables(database: str = None) -> List[str]:
            db = database or self.database
            response = self.client.list_table_metadata(
                CatalogName="AwsDataCatalog",
                DatabaseName=db
            )
            return [table["Name"] for table in response["TableMetadataList"]]
    
    async def execute(self, action: str, params: Dict[str, Any] = None) -> MCPResponse:
        if params is None:
            params = {}
        
        try:
            if action == "execute_query":
                query = params.get("query")
                database = params.get("database", self.database)
                response = self.client.start_query_execution(
                    QueryString=query,
                    QueryExecutionContext={"Database": database},
                    ResultConfiguration={"OutputLocation": self.output_location}
                )
                return MCPResponse(success=True, data={"execution_id": response["QueryExecutionId"]})
            
            elif action == "get_query_status":
                execution_id = params.get("execution_id")
                response = self.client.get_query_execution(QueryExecutionId=execution_id)
                return MCPResponse(success=True, data={
                    "state": response["QueryExecution"]["Status"]["State"],
                    "submission_time": str(response["QueryExecution"]["Status"]["SubmissionDateTime"]),
                    "completion_time": str(response["QueryExecution"]["Status"].get("CompletionDateTime", "")),
                })
            
            elif action == "get_query_results":
                execution_id = params.get("execution_id")
                max_results = params.get("max_results", 100)
                response = self.client.get_query_results(
                    QueryExecutionId=execution_id,
                    MaxResults=max_results
                )
                columns = [col["Name"] for col in response["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
                rows = []
                for row in response["ResultSet"]["Rows"][1:]:
                    rows.append([field.get("VarCharValue", "") for field in row["Data"]])
                
                return MCPResponse(success=True, data={"columns": columns, "rows": rows})
            
            elif action == "list_databases":
                response = self.client.list_databases(CatalogName="AwsDataCatalog")
                return MCPResponse(success=True, data=[db["Name"] for db in response["DatabaseList"]])
            
            elif action == "list_tables":
                database = params.get("database", self.database)
                response = self.client.list_table_metadata(
                    CatalogName="AwsDataCatalog",
                    DatabaseName=database
                )
                return MCPResponse(success=True, data=[table["Name"] for table in response["TableMetadataList"]])
            
            return MCPResponse(success=False, error=f"Unknown action: {action}")
        
        except Exception as e:
            return MCPResponse(success=False, error=str(e))
    
    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "execute_query",
                "description": "Execute SQL query on Athena",
                "parameters": {
                    "query": "string",
                    "database": "string (optional)"
                }
            },
            {
                "name": "get_query_status",
                "description": "Get query execution status",
                "parameters": {"execution_id": "string"}
            },
            {
                "name": "get_query_results",
                "description": "Get query results",
                "parameters": {
                    "execution_id": "string",
                    "max_results": "integer (optional, default 100)"
                }
            },
            {
                "name": "list_databases",
                "description": "List available databases",
                "parameters": {}
            },
            {
                "name": "list_tables",
                "description": "List tables in database",
                "parameters": {"database": "string (optional)"}
            }
        ]
    
    def get_resources(self) -> List[Dict[str, Any]]:
        return []
