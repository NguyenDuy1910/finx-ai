import boto3
from typing import Dict, List, Any, Optional


class AthenaSchemaReader:
    
    def __init__(
        self,
        database: str,
        region: str = "ap-southeast-1",
        profile: Optional[str] = None
    ):
        self.database = database
        self.region = region
        
        if profile:
            session = boto3.Session(profile_name=profile, region_name=region)
            self.glue = session.client("glue")
        else:
            self.glue = boto3.client("glue", region_name=region)
    
    def get_all_tables(self) -> List[str]:
        tables = []
        paginator = self.glue.get_paginator("get_tables")
        for page in paginator.paginate(DatabaseName=self.database):
            for table in page.get("TableList", []):
                tables.append(table["Name"])
        return tables
    
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        response = self.glue.get_table(
            DatabaseName=self.database,
            Name=table_name
        )
        table = response["Table"]
        
        columns = []
        for col in table.get("StorageDescriptor", {}).get("Columns", []):
            columns.append({
                "name": col["Name"],
                "type": col.get("Type", "string"),
                "description": col.get("Comment", "")
            })
        
        for col in table.get("PartitionKeys", []):
            columns.append({
                "name": col["Name"],
                "type": col.get("Type", "string"),
                "description": col.get("Comment", ""),
                "is_partition": True
            })
        
        return {
            "name": table_name,
            "description": table.get("Description", ""),
            "columns": columns,
            "location": table.get("StorageDescriptor", {}).get("Location", ""),
            "database": self.database
        }
    
    def get_all_schemas(self) -> List[Dict[str, Any]]:
        schemas = []
        tables = self.get_all_tables()
        for table_name in tables:
            schema = self.get_table_schema(table_name)
            schemas.append(schema)
        return schemas

