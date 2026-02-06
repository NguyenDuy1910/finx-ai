import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_graph import get_falkordb_client, GraphSchemaManager


def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    
    print(f"Connecting to FalkorDB at {host}:{port}")
    
    client = get_falkordb_client(host=host, port=port)
    manager = GraphSchemaManager(client)
    
    print("Initializing schema...")
    result = manager.initialize_schema()
    print(f"Schema initialized: {result}")
    
    print("Populating default patterns...")
    patterns = manager.populate_default_patterns()
    print(f"Patterns added: {patterns}")
    
    print("Done")


if __name__ == "__main__":
    main()

