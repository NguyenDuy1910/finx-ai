"""Pipeline engine — orchestrates the full 7-stage preprocessing workflow.

Enterprise Pipeline Stages
--------------------------
1. **Enterprise Sources**    — external systems (Confluence, Athena, S3, local)
2. **Source Adapters**       — fetch raw content → ``RawDocument``
3. **Raw Artifact Store**    — persist raw artifacts + manifest (optional)
4. **Input Router**          — classify content type → select extractor
5. **Parsing / Extraction**  — parse structure → ``CanonicalDocument``
6. **LLM Normalization**     — enrich with domain classification & entities
7. **Writer / Output**       — emit JSON for downstream ingestion

Usage
-----
    from pipeline.engine import PipelineEngine, PipelineConfig
    from pipeline.adapters.confluence import ConfluenceAdapter
    from pipeline.writers.json_writer import JSONWriter

    engine = PipelineEngine(
        config=PipelineConfig(use_llm_normalizer=True, save_raw_artifacts=True),
        writer=JSONWriter("output/pipeline"),
    )
    results = engine.run(ConfluenceAdapter())

    # Re-process from stored raw artifacts (no re-fetching)
    results = engine.reprocess()
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.adapters.base import BaseAdapter, RawDocument
from pipeline.artifact_store import RawArtifactStore
from pipeline.errors import (
    ErrorCategory,
    ErrorSeverity,
    ExtractionError,
    NormalizationError,
    PipelineError,
)
from pipeline.extractors.base import BaseExtractor
from pipeline.extractors.docling import DoclingExtractor
from pipeline.extractors.html import HTMLExtractor, MarkdownExtractor, SchemaExtractor
from pipeline.extractors.mineru import MinerUExtractor
from pipeline.normalizers.base import BaseNormalizer
from pipeline.normalizers.llm import LLMNormalizer, RuleBasedNormalizer
from pipeline.router import ContentCategory, InputRouter, classify
from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.provenance import ProcessingStage, ProcessingStep
from pipeline.writers.base import BaseWriter

log = logging.getLogger("finx-data.engine")


@dataclass
class PipelineConfig:
    """Configuration for the pipeline engine."""

    # Normalization
    use_llm_normalizer: bool = False
    llm_model: str | None = None
    min_words_for_llm: int = 20

    # Document extraction
    use_mineru: bool = True
    use_docling: bool = False
    mineru_output_dir: str | Path | None = None

    # Raw artifact storage (Stage 3)
    save_raw_artifacts: bool = False
    raw_artifact_dir: str | Path = "output/raw_artifacts"

    # Intermediate storage (between stages)
    save_intermediate: bool = False
    intermediate_dir: str | Path = "output/intermediate"

    # Processing
    skip_existing: bool = True
    max_errors: int = 100  # stop pipeline after this many errors
    llm_concurrency: int = 6  # concurrent LLM normalization calls
    min_doc_words: int = 10  # skip documents with fewer words than this

    # Logging
    log_every: int = 50  # log progress every N documents


@dataclass
class PipelineResult:
    """Summary of a pipeline run."""

    total_fetched: int = 0
    total_processed: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    errors: list[PipelineError] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    output_paths: list[str] = field(default_factory=list)

    def print_summary(self) -> None:
        log.info("=" * 60)
        log.info("Pipeline run summary")
        log.info("  Total fetched   : %d", self.total_fetched)
        log.info("  Processed       : %d", self.total_processed)
        log.info("  Skipped         : %d", self.total_skipped)
        log.info("  Errors          : %d", self.total_errors)
        log.info("  Elapsed         : %.1fs", self.elapsed_seconds)
        if self.total_processed > 0:
            log.info("  Avg per doc     : %.1fs", self.elapsed_seconds / self.total_processed)
        log.info("=" * 60)

        if self.errors:
            log.warning("Errors:")
            for err in self.errors[:10]:
                log.warning("  [%s] %s — %s", err.category.value, err.source_uri, err.message)
            if len(self.errors) > 10:
                log.warning("  ... and %d more", len(self.errors) - 10)


class PipelineEngine:
    """Orchestrates the full 7-stage preprocessing pipeline.

    Stages:
    1. Enterprise Sources (external)
    2. Adapter.fetch() → RawDocument
    3. ArtifactStore.store() — persist raw artifact (optional)
    4. InputRouter.route() — classify content → select extractor
    5. Extractor.extract() → CanonicalDocument
    6. Normalizer.normalize() → enriched CanonicalDocument
    7. Writer.write() → output files

    The engine provides deterministic routing via ``InputRouter`` instead
    of relying on implicit ``can_handle()`` chains.
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        writer: BaseWriter | None = None,
        extractors: list[BaseExtractor] | None = None,
        normalizers: list[BaseNormalizer] | None = None,
        router: InputRouter | None = None,
    ):
        self.config = config or PipelineConfig()
        self.writer = writer

        # Build default extractor stack (order matters — first match wins)
        if extractors is not None:
            self.extractors = extractors
        else:
            self.extractors = self._default_extractors()

        # Build normalizer stack
        if normalizers is not None:
            self.normalizers = normalizers
        else:
            self.normalizers = self._default_normalizers()

        # Build InputRouter (Stage 4)
        if router is not None:
            self.router = router
        else:
            self.router = self._default_router()

        # Artifact store (Stage 3) — lazy-init when needed
        self._artifact_store: RawArtifactStore | None = None

    def _default_extractors(self) -> list[BaseExtractor]:
        extractors: list[BaseExtractor] = []
        if self.config.use_docling:
            extractors.append(DoclingExtractor())
        if self.config.use_mineru:
            extractors.append(MinerUExtractor(output_dir=self.config.mineru_output_dir))
        extractors.extend([
            SchemaExtractor(),
            HTMLExtractor(),
            MarkdownExtractor(),
        ])
        return extractors

    def _default_normalizers(self) -> list[BaseNormalizer]:
        normalizers: list[BaseNormalizer] = [RuleBasedNormalizer()]
        if self.config.use_llm_normalizer:
            normalizers.append(
                LLMNormalizer(
                    model=self.config.llm_model,
                    skip_if_short=self.config.min_words_for_llm,
                )
            )
        return normalizers

    def _default_router(self) -> InputRouter:
        """Build the default InputRouter from the extractor stack.

        Maps each ContentCategory to the first extractor in the stack
        that can handle it, using the standard category→extractor mapping.
        """
        table: dict[ContentCategory, BaseExtractor] = {}

        # Find named extractors
        by_name: dict[str, BaseExtractor] = {}
        for ext in self.extractors:
            by_name[ext.name] = ext

        # Docling handles PDF, image, and Office formats (preferred over MinerU)
        if "docling_extractor" in by_name:
            table[ContentCategory.PDF] = by_name["docling_extractor"]
            table[ContentCategory.IMAGE] = by_name["docling_extractor"]

        # MinerU handles PDF and image (fallback if Docling not enabled)
        if "mineru_extractor" in by_name:
            if ContentCategory.PDF not in table:
                table[ContentCategory.PDF] = by_name["mineru_extractor"]
            if ContentCategory.IMAGE not in table:
                table[ContentCategory.IMAGE] = by_name["mineru_extractor"]

        # Schema extractor
        if "schema_extractor" in by_name:
            table[ContentCategory.SCHEMA] = by_name["schema_extractor"]

        # HTML extractor
        if "html_extractor" in by_name:
            table[ContentCategory.HTML] = by_name["html_extractor"]

        # Markdown extractor covers markdown, csv, json, plaintext
        if "markdown_extractor" in by_name:
            md = by_name["markdown_extractor"]
            for cat in (ContentCategory.MARKDOWN, ContentCategory.CSV,
                        ContentCategory.JSON, ContentCategory.PLAINTEXT):
                table[cat] = md

        return InputRouter(table)

    @property
    def artifact_store(self) -> RawArtifactStore | None:
        """Lazy-initialized artifact store."""
        if self.config.save_raw_artifacts and self._artifact_store is None:
            self._artifact_store = RawArtifactStore(self.config.raw_artifact_dir)
        return self._artifact_store

    def run(self, adapter: BaseAdapter) -> PipelineResult:
        """Execute the full 7-stage pipeline against a single adapter.

        When LLM normalization is enabled with ``llm_concurrency > 1``,
        documents are first extracted (stages 2-5), then LLM-normalized
        concurrently in batches for much faster throughput.
        """
        result = PipelineResult()
        t0 = time.monotonic()

        log.info("Pipeline starting — source=%s", adapter.source_system)

        # Separate normalizers into fast (rule-based) and LLM
        rule_normalizers = [n for n in self.normalizers if not isinstance(n, LLMNormalizer)]
        llm_normalizers = [n for n in self.normalizers if isinstance(n, LLMNormalizer)]
        use_concurrent_llm = (
            len(llm_normalizers) > 0
            and self.config.llm_concurrency > 1
        )

        # Accumulator for concurrent LLM normalization
        pending_docs: list[CanonicalDocument] = []
        batch_size = self.config.llm_concurrency * 2  # double the pool for pipelining

        def _flush_llm_batch(docs: list[CanonicalDocument]) -> None:
            """Normalize a batch of docs through LLM concurrently, then write."""
            if not docs:
                return

            def _llm_normalize(doc: CanonicalDocument) -> CanonicalDocument:
                for norm in llm_normalizers:
                    doc = norm.normalize(doc)
                return doc

            with ThreadPoolExecutor(max_workers=self.config.llm_concurrency) as pool:
                futures = {pool.submit(_llm_normalize, d): d for d in docs}
                for future in as_completed(futures):
                    try:
                        doc = future.result()
                        if self.config.save_intermediate:
                            self._save_stage(doc, "step2_normalized")
                        if self.writer:
                            path = self.writer.write(doc)
                            if path:
                                result.output_paths.append(path)
                                result.total_processed += 1
                                log.info("  ✓ [%d] %s — %s", result.total_processed, doc.title or doc.source_document_id, path)
                            else:
                                result.total_skipped += 1
                        else:
                            result.total_processed += 1
                            log.info("  ✓ [%d] %s", result.total_processed, doc.title or doc.source_document_id)
                    except Exception as exc:
                        original = futures[future]
                        error = PipelineError(
                            category=ErrorCategory.NORMALIZATION,
                            severity=ErrorSeverity.ERROR,
                            message=str(exc),
                            source_uri=original.source_uri,
                            stage="llm_normalize",
                            exception_type=type(exc).__name__,
                            retryable=True,
                        )
                        result.errors.append(error)
                        result.total_errors += 1
                        log.warning("LLM batch error %s: %s", original.source_uri, exc)

        try:
            for raw in self._iter_adapter(adapter, result):
                result.total_fetched += 1

                if result.total_errors >= self.config.max_errors:
                    log.error("Max errors reached (%d), stopping pipeline", self.config.max_errors)
                    break

                # Stage 3: Raw Artifact Store (optional)
                if self.artifact_store:
                    try:
                        self.artifact_store.store(raw)
                    except Exception as exc:
                        log.warning("Artifact store error for %s: %s", raw.source_uri, exc)

                try:
                    # Stages 4-5: Route + Extract
                    category, extractor = self.router.route(raw)
                    if extractor is None:
                        extractor = self._select_extractor(raw)
                    if extractor is None:
                        log.warning("No extractor for %s (category=%s)", raw.source_uri, category.value)
                        result.total_skipped += 1
                        continue

                    doc = extractor.extract(raw)

                    # Skip documents with no real content
                    if doc.word_count() < self.config.min_doc_words:
                        log.debug("Skipping low-value doc %s (%d words)", raw.source_uri, doc.word_count())
                        result.total_skipped += 1
                        continue

                    if self.config.save_intermediate:
                        self._save_stage(doc, "step1_extracted")

                    # Stage 6a: Rule-based normalization (always fast, in-line)
                    for norm in rule_normalizers:
                        doc = norm.normalize(doc)

                    if use_concurrent_llm:
                        # Queue for concurrent LLM normalization
                        pending_docs.append(doc)
                        if len(pending_docs) >= batch_size:
                            _flush_llm_batch(pending_docs)
                            pending_docs.clear()
                    else:
                        # Sequential LLM normalization (concurrency=1 or no LLM)
                        for norm in llm_normalizers:
                            doc = norm.normalize(doc)
                        if self.config.save_intermediate:
                            self._save_stage(doc, "step2_normalized")
                        if self.writer:
                            path = self.writer.write(doc)
                            if path:
                                result.output_paths.append(path)
                                result.total_processed += 1
                                log.info("  ✓ [%d] %s — %s", result.total_processed, doc.title or doc.source_document_id, path)
                            else:
                                result.total_skipped += 1
                        else:
                            result.total_processed += 1
                            log.info("  ✓ [%d] %s", result.total_processed, doc.title or doc.source_document_id)

                except Exception as exc:
                    error = PipelineError(
                        category=ErrorCategory.EXTRACTION,
                        severity=ErrorSeverity.ERROR,
                        message=str(exc),
                        source_uri=raw.source_uri,
                        stage="process_one",
                        exception_type=type(exc).__name__,
                        retryable=self._is_retryable(exc),
                    )
                    result.errors.append(error)
                    result.total_errors += 1
                    log.warning("Error processing %s: %s", raw.source_uri, exc)

                # Progress logging
                done = result.total_processed + result.total_skipped + result.total_errors
                if done > 0 and done % self.config.log_every == 0:
                    elapsed = time.monotonic() - t0
                    log.info(
                        "  Progress: %d fetched, %d processed, %d skipped, %d errors (%.1fs)",
                        result.total_fetched,
                        result.total_processed,
                        result.total_skipped,
                        result.total_errors,
                        elapsed,
                    )

            # Flush remaining LLM batch
            if pending_docs:
                _flush_llm_batch(pending_docs)
                pending_docs.clear()

        finally:
            if self.artifact_store:
                self.artifact_store.flush()
            if self.writer:
                self.writer.flush()

        result.elapsed_seconds = time.monotonic() - t0
        result.print_summary()
        return result

    def reprocess(self) -> PipelineResult:
        """Re-process documents from the Raw Artifact Store without re-fetching.

        This loads previously stored raw artifacts and runs them through
        stages 4–7 (router → extraction → normalization → writing).
        Requires ``save_raw_artifacts`` to have been enabled in a prior run.
        """
        store = RawArtifactStore(self.config.raw_artifact_dir)
        if store.manifest.count == 0:
            log.warning("No stored artifacts found in %s", self.config.raw_artifact_dir)
            return PipelineResult()

        result = PipelineResult()
        t0 = time.monotonic()
        log.info("Reprocessing %d stored artifacts from %s", store.manifest.count, self.config.raw_artifact_dir)

        docs = store.iter_stored()
        result.total_fetched = len(docs)

        try:
            for raw in docs:
                if result.total_errors >= self.config.max_errors:
                    log.error("Max errors reached (%d), stopping", self.config.max_errors)
                    break

                try:
                    doc = self._process_one(raw)
                    if doc and self.writer:
                        path = self.writer.write(doc)
                        if path:
                            result.output_paths.append(path)
                            result.total_processed += 1
                        else:
                            result.total_skipped += 1
                    elif doc:
                        result.total_processed += 1
                    else:
                        result.total_skipped += 1
                except Exception as exc:
                    error = PipelineError(
                        category=ErrorCategory.EXTRACTION,
                        severity=ErrorSeverity.ERROR,
                        message=str(exc),
                        source_uri=raw.source_uri,
                        stage="reprocess",
                        exception_type=type(exc).__name__,
                        retryable=False,
                    )
                    result.errors.append(error)
                    result.total_errors += 1
                    log.warning("Reprocess error %s: %s", raw.source_uri, exc)
        finally:
            if self.writer:
                self.writer.flush()

        result.elapsed_seconds = time.monotonic() - t0
        result.print_summary()
        return result

    @staticmethod
    def _iter_adapter(adapter: BaseAdapter, result: PipelineResult):
        """Iterate adapter.fetch(), catching errors in the generator itself."""
        it = adapter.fetch()
        while True:
            try:
                yield next(it)
            except StopIteration:
                return
            except Exception as exc:
                error = PipelineError(
                    category=ErrorCategory.INGESTION,
                    severity=ErrorSeverity.ERROR,
                    message=str(exc),
                    stage="adapter.fetch",
                    exception_type=type(exc).__name__,
                    retryable=True,
                )
                result.errors.append(error)
                result.total_errors += 1
                log.warning("Adapter fetch error: %s", exc)
                return

    def process_single(self, raw: RawDocument) -> CanonicalDocument | None:
        """Process a single RawDocument through the pipeline. Public convenience method."""
        return self._process_one(raw)

    def _process_one(self, raw: RawDocument) -> CanonicalDocument | None:
        """Process a single document through routing → extraction → normalization."""
        # Stage 4: Input Router — classify and select extractor
        category, extractor = self.router.route(raw)
        if extractor is None:
            # Fallback: try legacy can_handle() chain
            extractor = self._select_extractor(raw)
        if extractor is None:
            log.warning("No extractor for %s (category=%s, mime=%s)", raw.source_uri, category.value, raw.mime_type)
            return None

        # Stage 5: Extract
        doc = extractor.extract(raw)

        # Skip documents with no real content
        if doc.word_count() < self.config.min_doc_words:
            log.debug("Skipping low-value doc %s (%d words)", raw.source_uri, doc.word_count())
            return None

        if self.config.save_intermediate:
            self._save_stage(doc, "step1_extracted")

        # Stage 6: Normalize
        for normalizer in self.normalizers:
            doc = normalizer.normalize(doc)
        if self.config.save_intermediate:
            self._save_stage(doc, "step2_normalized")

        return doc

    def _save_stage(self, doc: CanonicalDocument, stage: str) -> None:
        """Save intermediate document to disk for debugging/inspection."""
        stage_dir = Path(self.config.intermediate_dir) / stage
        stage_dir.mkdir(parents=True, exist_ok=True)

        safe_name = doc.source_document_id or doc.title or doc.document_id[:16]
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in safe_name)
        path = stage_dir / f"{safe_name}.json"

        data = json.loads(doc.model_dump_json())
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        log.debug("Saved %s → %s", stage, path)

    def _select_extractor(self, raw: RawDocument) -> BaseExtractor | None:
        """Select the first extractor that can handle this document."""
        for ext in self.extractors:
            if ext.can_handle(raw):
                return ext
        return None

    def _is_retryable(self, exc: Exception) -> bool:
        """Determine if an exception is transient and worth retrying."""
        retryable_types = ("ConnectionError", "TimeoutError", "HTTPError")
        return type(exc).__name__ in retryable_types


def run_pipeline(
    adapter: BaseAdapter,
    output_dir: str | Path = "output/pipeline",
    *,
    use_llm: bool = False,
    use_docling: bool = False,
    llm_model: str | None = None,
    llm_concurrency: int = 4,
    min_doc_words: int = 10,
    format: str = "canonical",
    overwrite: bool = False,
    save_intermediate: bool = False,
    intermediate_dir: str | Path | None = None,
    save_raw_artifacts: bool = False,
    raw_artifact_dir: str | Path | None = None,
) -> PipelineResult:
    """Convenience function to run a full pipeline with sensible defaults."""
    from pipeline.writers.json_writer import JSONWriter, ProgressTrackingWriter

    config = PipelineConfig(
        use_llm_normalizer=use_llm,
        use_docling=use_docling,
        llm_model=llm_model,
        llm_concurrency=llm_concurrency,
        min_doc_words=min_doc_words,
        save_intermediate=save_intermediate,
        intermediate_dir=intermediate_dir or Path(output_dir) / "intermediate",
        save_raw_artifacts=save_raw_artifacts,
        raw_artifact_dir=raw_artifact_dir or Path(output_dir) / "raw_artifacts",
    )

    json_writer = JSONWriter(output_dir, format=format, overwrite=overwrite)
    progress_file = Path(output_dir) / ".pipeline_progress.json"
    writer = ProgressTrackingWriter(json_writer, progress_file)

    engine = PipelineEngine(config=config, writer=writer)
    return engine.run(adapter)
