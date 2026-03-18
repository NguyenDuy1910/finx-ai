"""Pipeline error types and failure tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ErrorSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class ErrorCategory(str, Enum):
    INGESTION = "ingestion"
    EXTRACTION = "extraction"
    NORMALIZATION = "normalization"
    VALIDATION = "validation"
    IO = "io"
    TIMEOUT = "timeout"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"


@dataclass
class PipelineError:
    """Structured error record for audit and retry decisions."""

    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    source_uri: str = ""
    stage: str = ""
    exception_type: str = ""
    retryable: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "source_uri": self.source_uri,
            "stage": self.stage,
            "exception_type": self.exception_type,
            "retryable": self.retryable,
            "timestamp": self.timestamp.isoformat(),
        }


class PipelineException(Exception):
    """Base exception for pipeline operations."""

    def __init__(self, message: str, error: PipelineError | None = None):
        super().__init__(message)
        self.error = error


class ExtractionError(PipelineException):
    """Raised when content extraction fails."""


class NormalizationError(PipelineException):
    """Raised when LLM normalization fails."""


class AdapterError(PipelineException):
    """Raised when a source adapter fails to fetch content."""
