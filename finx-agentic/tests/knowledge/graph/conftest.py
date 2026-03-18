from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock


def _stub(name: str, attrs: dict | None = None) -> None:
    if name not in sys.modules:
        mod = ModuleType(name)
        for k, v in (attrs or {}).items():
            setattr(mod, k, v)
        sys.modules[name] = mod


_stub("falkordb", {"FalkorDB": MagicMock(), "Graph": MagicMock()})
_stub("src.knowledge.graph.store", {"GraphStore": MagicMock(), "BaseKVStorage": object})
_stub("src.knowledge.graph.merger", {"Merger": MagicMock()})
