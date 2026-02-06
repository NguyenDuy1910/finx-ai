from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from .types import MCPConfig, MCPResponse


class BaseMCPProvider(ABC):
    def __init__(self, config: MCPConfig):
        self.config = config
        self.mcp = FastMCP(name=config.name)
        self._setup()
    
    @abstractmethod
    def _setup(self) -> None:
        pass
    
    @abstractmethod
    async def execute(self, *args, **kwargs) -> MCPResponse:
        pass
    
    @abstractmethod
    def get_tools(self) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def get_resources(self) -> List[Dict[str, Any]]:
        pass
    
    def is_enabled(self) -> bool:
        return self.config.enabled
    
    def get_name(self) -> str:
        return self.config.name
    
    def get_mcp_instance(self) -> FastMCP:
        return self.mcp
