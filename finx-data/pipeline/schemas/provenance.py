"""Processing provenance and lineage tracking.

Every stage in the pipeline appends a ``ProcessingStep`` to the document's
provenance record, creating a full audit trail from raw source to final
canonical output.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProcessingStage(str, Enum):
    """Named stages in the preprocessing pipeline."""

    INGESTION = "ingestion"
    EXTRACTION = "extraction"
    NORMALIZATION = "normalization"
    ENRICHMENT = "enrichment"
    VALIDATION = "validation"
    OUTPUT = "output"


class ProcessingStep(BaseModel):
    """A single processing step in the document's provenance chain."""

    stage: ProcessingStage
    processor: str = Field(
        ..., description="Name of the module/class that performed this step"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float | None = Field(
        None, description="Wall-clock time for this step in milliseconds"
    )
    input_hash: str | None = Field(
        None, description="SHA-256 of the input to this step for idempotency checks"
    )
    output_hash: str | None = Field(
        None, description="SHA-256 of the output from this step"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration parameters used in this step",
    )
    error: str | None = None


class QualitySignal(BaseModel):
    """Quality and confidence indicators for the processed document."""

    extraction_confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="How confident the extractor is in the parse"
    )
    content_completeness: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Estimated fraction of original content preserved",
    )
    has_tables: bool = False
    has_images: bool = False
    has_code: bool = False
    word_count: int = 0
    language_detected: str | None = None
    parsing_warnings: list[str] = Field(default_factory=list)
    flags: dict[str, bool] = Field(
        default_factory=dict,
        description="Arbitrary quality flags, e.g. {'low_quality': True, 'needs_review': True}",
    )


class Provenance(BaseModel):
    """Full processing provenance for a canonical document."""

    pipeline_version: str = ""
    steps: list[ProcessingStep] = Field(default_factory=list)
    quality: QualitySignal = Field(default_factory=QualitySignal)

    def add_step(self, step: ProcessingStep) -> None:
        self.steps.append(step)

    @property
    def last_stage(self) -> ProcessingStage | None:
        return self.steps[-1].stage if self.steps else None

    @property
    def has_errors(self) -> bool:
        return any(s.error is not None for s in self.steps)
