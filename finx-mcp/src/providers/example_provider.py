from typing import Any, Dict, List

from ..core.provider import BaseMCPProvider
from ..core.types import MCPResponse


class ExampleProvider(BaseMCPProvider):
    def _setup(self) -> None:
        @self.mcp.tool()
        def example_tool(input_text: str) -> str:
            return f"Processed: {input_text}"
    
    async def execute(self, action: str, params: Dict[str, Any] = None) -> MCPResponse:
        if params is None:
            params = {}
        
        try:
            if action == "process":
                result = f"Processed with {self.config.name}"
                return MCPResponse(success=True, data=result)
            
            return MCPResponse(
                success=False, 
                error=f"Unknown action: {action}"
            )
        except Exception as e:
            return MCPResponse(success=False, error=str(e))
    
    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "example_tool",
                "description": "Example tool implementation",
                "parameters": {"input_text": "string"}
            }
        ]
    
    def get_resources(self) -> List[Dict[str, Any]]:
        return []
