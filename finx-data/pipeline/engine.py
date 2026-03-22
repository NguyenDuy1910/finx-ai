"""Pipeline engine -- fetch -> extract -> clean -> normalize -> chunk -> write."""

from __future__ import annotations

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.adapters.base import BaseAdapter, RawDocument
from pipeline.chunkers.router import ChunkerRouter
from pipeline.extractors.base import BaseExtractor
from pipeline.extractors.html import HTMLExtractor, MarkdownExtractor
from pipeline.normalizers.base import BaseNormalizer
from pipeline.normalizers.cleaning import CleaningNormalizer
from pipeline.normalizers.llm import LLMNormalizer, RuleBasedNormalizer
from pipeline.router import ContentCategory, InputRouter
from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.chunk import ChunkDocument
from pipeline.writers.base import BaseWriter
from pipeline.writers.chunk_writer import ChunkWriter

log = logging.getLogger("finx-data.engine")

PIPELINE_VERSION = "2.0.0"


@dataclass
class PipelineConfig:
    use_llm_normalizer: bool = False
    llm_model: str | None = None
    min_words_for_llm: int = 20
    use_docling: bool = True
    max_errors: int = 100
    llm_concurrency: int = 6
    min_doc_words: int = 10
    log_every: int = 50
    # Chunking configuration
    enable_chunking: bool = False
    chunk_output_dir: str | Path = "output/chunks"
    max_chunk_tokens: int = 400
    chunk_overlap_tokens: int = 50
    min_chunk_words: int = 10
    default_tenant_id: str = "default"


@dataclass
class PipelineResult:
    total_fetched: int = 0
    total_processed: int = 0
    total_chunks: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    errors: list[dict] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    chunk_kind_counts: dict[str, int] = field(default_factory=dict)

    def print_summary(self):
        log.info("=" * 60)
        log.info("Pipeline: %d fetched, %d processed, %d chunks, %d skipped, %d errors in %.1fs",
                 self.total_fetched, self.total_processed, self.total_chunks,
                 self.total_skipped, self.total_errors, self.elapsed_seconds)
        if self.chunk_kind_counts:
            breakdown = ", ".join(f"{k}={v}" for k, v in sorted(self.chunk_kind_counts.items()))
            log.info("Chunk kinds: %s", breakdown)
        log.info("=" * 60)


class PipelineEngine:
    def __init__(
        self,
        config: PipelineConfig | None = None,
        writer: BaseWriter | None = None,
        extractors: list[BaseExtractor] | None = None,
        normalizers: list[BaseNormalizer] | None = None,
        router: InputRouter | None = None,
        chunker_router: ChunkerRouter | None = None,
        chunk_writer: ChunkWriter | None = None,
    ):
        self.config = config or PipelineConfig()
        self.writer = writer
        self.extractors = extractors if extractors is not None else self._default_extractors()
        self.normalizers = normalizers if normalizers is not None else self._default_normalizers()
        self.router = router if router is not None else self._default_router()
        # Chunking
        self.chunker_router = chunker_router if chunker_router is not None else self._default_chunker_router()
        self.chunk_writer = chunk_writer

    def _default_extractors(self) -> list[BaseExtractor]:
        extractors: list[BaseExtractor] = []
        if self.config.use_docling:
            try:
                from pipeline.extractors.docling import DoclingExtractor
                extractors.append(DoclingExtractor())
            except ImportError:
                log.warning("Docling not installed, skipping DoclingExtractor")
        # VLM extractor for image attachments
        try:
            from pipeline.extractors.vlm import VLMExtractor
            extractors.append(VLMExtractor())
        except ImportError:
            log.debug("VLMExtractor not available")
        extractors.extend([HTMLExtractor(), MarkdownExtractor()])
        return extractors

    def _default_normalizers(self) -> list[BaseNormalizer]:
        normalizers: list[BaseNormalizer] = [CleaningNormalizer(), RuleBasedNormalizer()]
        if self.config.use_llm_normalizer:
            normalizers.append(LLMNormalizer(model=self.config.llm_model, skip_if_short=self.config.min_words_for_llm))
        return normalizers

    def _default_chunker_router(self) -> ChunkerRouter:
        return ChunkerRouter(
            max_tokens=self.config.max_chunk_tokens,
            overlap_tokens=self.config.chunk_overlap_tokens,
            min_chunk_words=self.config.min_chunk_words,
            default_tenant_id=self.config.default_tenant_id,
        )

    def _default_router(self) -> InputRouter:
        table: dict[ContentCategory, BaseExtractor] = {}
        by_name: dict[str, BaseExtractor] = {ext.name: ext for ext in self.extractors}

        if "docling_extractor" in by_name:
            docling = by_name["docling_extractor"]
            for cat in (ContentCategory.PDF, ContentCategory.DOCX,
                        ContentCategory.PPTX, ContentCategory.XLSX):
                table[cat] = docling
            # Docling handles IMAGE only if VLM is not available
            if "vlm_extractor" not in by_name:
                table[ContentCategory.IMAGE] = docling

        # VLM extractor is preferred for standalone images
        if "vlm_extractor" in by_name:
            table[ContentCategory.IMAGE] = by_name["vlm_extractor"]

        if "html_extractor" in by_name:
            table[ContentCategory.HTML] = by_name["html_extractor"]
        if "markdown_extractor" in by_name:
            md = by_name["markdown_extractor"]
            for cat in (ContentCategory.MARKDOWN, ContentCategory.CSV, ContentCategory.JSON, ContentCategory.PLAINTEXT):
                table[cat] = md

        # ── Confluence extractors ─────────────────────────────────────
        try:
            from pipeline.extractors.confluence_page import ConfluencePageExtractor
            conf_page = ConfluencePageExtractor()
            table[ContentCategory.CONFLUENCE_PAGE] = conf_page
        except ImportError:
            log.debug("ConfluencePageExtractor not available")

        try:
            from pipeline.extractors.confluence_comment import ConfluenceCommentExtractor
            table[ContentCategory.CONFLUENCE_COMMENT] = ConfluenceCommentExtractor()
        except ImportError:
            log.debug("ConfluenceCommentExtractor not available")

        # Confluence attachments: reuse docling or VLM depending on sub-type
        # (the router already classifies attachments as PDF/IMAGE/DOCX/etc.
        #  so they fall through to the docling/image entries above)

        # ── Jira extractors ───────────────────────────────────────────
        try:
            from pipeline.extractors.jira_issue import JiraIssueExtractor
            jira_ext = JiraIssueExtractor()
            table[ContentCategory.JIRA_ISSUE] = jira_ext
            table[ContentCategory.JIRA_COMMENT] = jira_ext
        except ImportError:
            log.debug("JiraIssueExtractor not available")

        # Jira attachments: same as Confluence — sub-classified by MIME
        # and handled by docling/image extractors above

        return InputRouter(table)

    @staticmethod
    def _safe_fetch(adapter, result):
        it = adapter.fetch()
        while True:
            try:
                yield next(it)
            except StopIteration:
                return
            except Exception as exc:
                result.total_errors += 1
                result.errors.append({"uri": "", "error": str(exc)})
                log.warning("Adapter fetch error: %s", exc)
                return

    def run(self, adapter: BaseAdapter) -> PipelineResult:
        result = PipelineResult()
        t0 = time.monotonic()
        log.info("Pipeline starting -- source=%s", adapter.source_system)

        rule_normalizers = [n for n in self.normalizers if not isinstance(n, LLMNormalizer)]
        llm_normalizers = [n for n in self.normalizers if isinstance(n, LLMNormalizer)]
        use_concurrent_llm = len(llm_normalizers) > 0 and self.config.llm_concurrency > 1

        pending_docs: list[CanonicalDocument] = []
        batch_size = self.config.llm_concurrency * 2

        def _write_doc(doc: CanonicalDocument):
            if self.writer:
                path = self.writer.write(doc)
                if path:
                    result.total_processed += 1
                    log.info("  [%d] %s", result.total_processed, doc.title or doc.source_document_id)
                else:
                    result.total_skipped += 1
            else:
                result.total_processed += 1

            # Chunking stage: chunk the document and write chunks
            if self.config.enable_chunking:
                try:
                    chunker = self.chunker_router.route(doc)
                    chunks = chunker.chunk(doc)
                    result.total_chunks += len(chunks)
                    for c in chunks:
                        kind_name = c.chunk_kind.value
                        result.chunk_kind_counts[kind_name] = result.chunk_kind_counts.get(kind_name, 0) + 1
                    if self.chunk_writer and chunks:
                        self.chunk_writer.write_chunks(chunks)
                    log.debug("  Chunked %s → %d chunks", doc.title or doc.document_id[:12], len(chunks))
                except Exception as exc:
                    log.warning("Chunking error for %s: %s", doc.source_uri, exc)

        def _flush_llm_batch(docs: list[CanonicalDocument]):
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
                        _write_doc(future.result())
                    except Exception as exc:
                        original = futures[future]
                        result.total_errors += 1
                        result.errors.append({"uri": original.source_uri, "error": str(exc)})
                        log.warning("LLM error %s: %s", original.source_uri, exc)

        # Pre-load set of already-processed document IDs for checkpoint/resume
        _done_ids: set[str] = set()
        if self.writer and hasattr(self.writer, "processed_ids"):
            _done_ids = self.writer.processed_ids
            if _done_ids:
                log.info("Checkpoint: %d documents already processed — will skip them", len(_done_ids))

        try:
            for raw in self._safe_fetch(adapter, result):
                result.total_fetched += 1

                if result.total_errors >= self.config.max_errors:
                    log.error("Max errors reached (%d), stopping", self.config.max_errors)
                    break

                if _done_ids:
                    raw_key = f"{raw.source_system}::{raw.source_uri}"
                    predicted_doc_id = hashlib.sha256(raw_key.encode()).hexdigest()
                    if predicted_doc_id in _done_ids:
                        log.debug("Checkpoint skip: %s (%s)", raw.title or raw.source_uri, predicted_doc_id[:12])
                        result.total_skipped += 1
                        continue

                try:
                    _, extractor = self.router.route(raw)
                    if extractor is None:
                        result.total_skipped += 1
                        continue

                    doc = extractor.extract(raw)

                    # Stamp pipeline version on provenance
                    doc.provenance.pipeline_version = PIPELINE_VERSION

                    if doc.word_count() < self.config.min_doc_words:
                        result.total_skipped += 1
                        continue

                    for norm in rule_normalizers:
                        doc = norm.normalize(doc)

                    # Post-clean quality gate: re-check after cleaning removed noise
                    post_clean_words = doc.word_count()
                    if post_clean_words < self.config.min_doc_words:
                        log.debug("Skipping %s after cleaning (%d words)",
                                  doc.title or doc.source_uri, post_clean_words)
                        result.total_skipped += 1
                        continue

                    # Skip docs dominated by empty tables (spreadsheet noise)
                    table_blocks = [
                        b for b in doc.content_blocks
                        if hasattr(b, "block_type") and b.block_type.value == "table"
                    ]
                    if table_blocks:
                        empty_tables = [t for t in table_blocks if not t.rows]
                        meaningful_blocks = len(doc.content_blocks) - len(empty_tables)
                        if meaningful_blocks < 2 and post_clean_words < 50:
                            log.debug("Skipping %s — only %d meaningful blocks, %d words",
                                      doc.title or doc.source_uri, meaningful_blocks, post_clean_words)
                            result.total_skipped += 1
                            continue

                    if use_concurrent_llm:
                        pending_docs.append(doc)
                        if len(pending_docs) >= batch_size:
                            _flush_llm_batch(pending_docs)
                            pending_docs.clear()
                    else:
                        for norm in llm_normalizers:
                            doc = norm.normalize(doc)
                        _write_doc(doc)

                except Exception as exc:
                    result.total_errors += 1
                    result.errors.append({"uri": raw.source_uri, "error": str(exc)})
                    log.warning("Error processing %s: %s", raw.source_uri, exc)

                done = result.total_processed + result.total_skipped + result.total_errors
                if done > 0 and done % self.config.log_every == 0:
                    elapsed = time.monotonic() - t0
                    log.info("  Progress: %d/%d (%.1fs)", result.total_processed, result.total_fetched, elapsed)

            if pending_docs:
                _flush_llm_batch(pending_docs)

        finally:
            if self.writer:
                self.writer.flush()
            if self.chunk_writer:
                self.chunk_writer.flush()

        result.elapsed_seconds = time.monotonic() - t0
        result.print_summary()
        return result


def run_pipeline(
    adapter: BaseAdapter,
    output_dir: str | Path = "output/pipeline",
    *,
    use_llm: bool = False,
    use_docling: bool = True,
    llm_model: str | None = None,
    llm_concurrency: int = 4,
    min_doc_words: int = 10,
    format: str = "canonical",
    overwrite: bool = False,
    enable_chunking: bool = False,
    chunk_output_dir: str | Path | None = None,
    max_chunk_tokens: int = 400,
    chunk_overlap_tokens: int = 50,
    default_tenant_id: str = "default",
) -> PipelineResult:
    from pipeline.writers.json_writer import JSONWriter, ProgressTrackingWriter

    config = PipelineConfig(
        use_llm_normalizer=use_llm,
        use_docling=use_docling,
        llm_model=llm_model,
        llm_concurrency=llm_concurrency,
        min_doc_words=min_doc_words,
        enable_chunking=enable_chunking,
        max_chunk_tokens=max_chunk_tokens,
        chunk_overlap_tokens=chunk_overlap_tokens,
        default_tenant_id=default_tenant_id,
    )

    if chunk_output_dir:
        config.chunk_output_dir = chunk_output_dir

    json_writer = JSONWriter(output_dir, format=format, overwrite=overwrite)
    progress_file = Path(output_dir) / ".pipeline_progress.json"
    writer = ProgressTrackingWriter(json_writer, progress_file)

    chunk_writer_inst = None
    if enable_chunking:
        chunk_dir = Path(chunk_output_dir) if chunk_output_dir else Path(output_dir) / "chunks"
        chunk_writer_inst = ChunkWriter(chunk_dir, overwrite=overwrite)

    engine = PipelineEngine(config=config, writer=writer, chunk_writer=chunk_writer_inst)
    return engine.run(adapter)
