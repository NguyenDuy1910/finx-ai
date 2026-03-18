try:
    from src.core.graph.ontology import EDGE_TYPE_MAP, EDGE_TYPES, ENTITY_TYPES
except ImportError:
    EDGE_TYPE_MAP = {}  # type: ignore[assignment]
    EDGE_TYPES = []  # type: ignore[assignment]
    ENTITY_TYPES = []  # type: ignore[assignment]

try:
    from src.knowledge.indexing import SchemaMetadataWorkflow, DocumentIngestionWorkflow
    from src.knowledge.indexing.workflow import IndexingWorkflow
except ImportError:
    SchemaMetadataWorkflow = None  # type: ignore[assignment,misc]
    DocumentIngestionWorkflow = None  # type: ignore[assignment,misc]
    IndexingWorkflow = None  # type: ignore[assignment,misc]

__all__ = [
    "ENTITY_TYPES",
    "EDGE_TYPES",
    "EDGE_TYPE_MAP",
    "SchemaMetadataWorkflow",
    "DocumentIngestionWorkflow",
    "IndexingWorkflow",
]
