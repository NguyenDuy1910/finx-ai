class Text2SQLError(Exception):
    pass


class SchemaNotFoundError(Text2SQLError):
    pass


class SQLGenerationError(Text2SQLError):
    pass


class ValidationError(Text2SQLError):
    pass


class KnowledgeGraphError(Text2SQLError):
    pass


class AthenaExecutionError(Text2SQLError):
    pass

