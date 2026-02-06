import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_graph_schema.schema_builder import build_from_athena


def main():
    database = os.getenv("ATHENA_DATABASE", "non_prod_uat_gold_zone")
    region = os.getenv("AWS_REGION", "ap-southeast-1")
    profile = os.getenv("AWS_PROFILE")
    output_dir = os.getenv("SCHEMA_OUTPUT_DIR", "graph_schemas")
    
    tables_env = os.getenv("TABLES")
    tables = tables_env.split(",") if tables_env else None
    
    print(f"Database: {database}")
    print(f"Region: {region}")
    print(f"Output: {output_dir}")
    print(f"Tables: {tables or 'all'}")
    print("-" * 40)
    
    output_files = build_from_athena(
        database=database,
        output_dir=output_dir,
        region=region,
        profile=profile,
        tables=tables
    )
    
    print("-" * 40)
    print(f"Generated {len(output_files)} schema files")
    for f in output_files:
        print(f"  {f}")


if __name__ == "__main__":
    main()

