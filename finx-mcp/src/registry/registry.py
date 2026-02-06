from typing import Dict, List, Optional, Type

from ..core.provider import BaseMCPProvider
from ..core.types import MCPConfig
from ..providers.example_provider import ExampleProvider
from ..providers.athena_provider import AthenaProvider


class MCPRegistry:
    def __init__(self):
        self._providers: Dict[str, BaseMCPProvider] = {}
        self._provider_classes: Dict[str, Type[BaseMCPProvider]] = {
            "example": ExampleProvider,
            "athena": AthenaProvider,
        }
    
    def register_provider_class(
        self, 
        name: str, 
        provider_class: Type[BaseMCPProvider]
    ) -> None:
        self._provider_classes[name] = provider_class
    
    def create_provider(
        self, 
        name: str, 
        config: Optional[MCPConfig] = None
    ) -> BaseMCPProvider:
        if name not in self._provider_classes:
            raise ValueError(f"Provider '{name}' not registered")
        
        if config is None:
            config = MCPConfig(name=name)
        
        provider_class = self._provider_classes[name]
        provider = provider_class(config)
        self._providers[name] = provider
        return provider
    
    def get_provider(self, name: str) -> Optional[BaseMCPProvider]:
        return self._providers.get(name)
    
    def list_providers(self) -> List[str]:
        return list(self._providers.keys())
    
    def list_available_providers(self) -> List[str]:
        return list(self._provider_classes.keys())
    
    def remove_provider(self, name: str) -> bool:
        if name in self._providers:
            del self._providers[name]
            return True
        return False
