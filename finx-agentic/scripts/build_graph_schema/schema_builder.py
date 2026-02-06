import os
import json
from pathlib import Path
from typing import List, Optional
from .athena_reader import AthenaSchemaReader
from .domain_generator import DomainGenerator


class GraphSchemaBuilder:
    
    def __init__(
        self,
        database: str,
        output_dir: str = "graph_schemas",
        region: str = "ap-southeast-1",
        profile: Optional[str] = None
    ):
        self.database = database
        self.output_dir = Path(output_dir)
        self.reader = AthenaSchemaReader(database, region, profile)
        self.generator = DomainGenerator()
    
    def build_all(self, tables: Optional[List[str]] = None) -> List[str]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if tables:
            table_list = tables
        else:
            table_list = self.reader.get_all_tables()
        
        output_files = []
        
        for table_name in table_list:
            print(f"Processing: {table_name}")
            output_file = self.build_table(table_name)
            output_files.append(output_file)
        
        self._build_index(output_files)
        
        return output_files
    
    def build_table(self, table_name: str) -> str:
        schema = self.reader.get_table_schema(table_name)
        enriched = self.generator.generate_domain_terms(schema)
        
        output_file = self.output_dir / f"{table_name}.json"
        with open(output_file, "w") as f:
            json.dump(enriched, f, indent=2)
        
        return str(output_file)
    
    def _build_index(self, files: List[str]) -> str:
        index = {
            "database": self.database,
            "tables": [Path(f).stem for f in files],
            "count": len(files)
        }
        
        index_file = self.output_dir / "_index.json"
        with open(index_file, "w") as f:
            json.dump(index, f, indent=2)
        
        return str(index_file)


def build_from_athena(
    database: str,
    output_dir: str = "graph_schemas",
    region: str = "ap-southeast-1",
    profile: Optional[str] = None,
    tables: Optional[List[str]] = None
) -> List[str]:
    builder = GraphSchemaBuilder(database, output_dir, region, profile)
    return builder.build_all(tables)

