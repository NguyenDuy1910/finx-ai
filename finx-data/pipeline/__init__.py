"""finx-data preprocessing pipeline.

A modular, enterprise-grade 7-stage pipeline that transforms raw content
from multiple source adapters into a canonical normalized format suitable
for downstream vector-DB and graph-DB ingestion.

Architecture (7 Stages)
-----------------------
1. Enterprise Sources → 2. Source Adapters → 3. Raw Artifact Store →
4. Input Router → 5. Extraction (MinerU) → 6. LLM Normalization →
7. Writers (JSON/batch)

All stages communicate through the canonical ``CanonicalDocument`` schema.
"""

__version__ = "0.3.0"
