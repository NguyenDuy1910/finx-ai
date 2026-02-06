import asyncio

from src import MCPRegistry
from src.core.types import MCPConfig


async def main():
    registry = MCPRegistry()
    
    config = MCPConfig(
        name="example",
        enabled=True,
        settings={"mode": "demo"}
    )
    
    provider = registry.create_provider("example", config)
    
    print(f"Provider: {provider.get_name()}")
    print(f"Enabled: {provider.is_enabled()}")
    print(f"Tools: {provider.get_tools()}")
    
    response = await provider.execute("process", {"data": "test"})
    print(f"Response: {response}")


if __name__ == "__main__":
    asyncio.run(main())
