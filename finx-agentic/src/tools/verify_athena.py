import inspect
import sys
import os

# Add the project root to sys.path so we can import the module
# We range assuming this script is in src/tools/
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
sys.path.append(project_root)

try:
    import unittest.mock
    sys.modules["boto3"] = unittest.mock.MagicMock()
    from src.tools.aws_athena import AWSAthenaTools
    print("Successfully imported AWSAthenaTools")
except ImportError as e:
    print(f"Failed to import AWSAthenaTools: {e}")
    sys.exit(1)

def verify_methods():
    tools = AWSAthenaTools(region_name="us-east-1")
    
    expected_methods = [
        "start_query_execution",
        "get_query_execution",
        "get_query_results",
        "run_query",
        "list_databases",
        "list_tables",
        "get_table_metadata"
    ]
    
    missing_methods = []
    for method in expected_methods:
        if not hasattr(tools, method):
            missing_methods.append(method)
        else:
            print(f"Method found: {method}")
            # print signature
            sig = inspect.signature(getattr(tools, method))
            print(f"  Signature: {sig}")

    if missing_methods:
        print(f"Missing methods: {missing_methods}")
        sys.exit(1)
    else:
        print("All expected methods are present.")

if __name__ == "__main__":
    # Mock boto3 to avoid actual AWS calls during init if credentials aren't set
    import unittest.mock
    with unittest.mock.patch("boto3.client"):
        verify_methods()
