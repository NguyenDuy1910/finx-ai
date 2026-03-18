from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from src.core.llm.protocol import LLMAdapter
from .models import Chunk, ExtractionResult, RawEdge, RawNode
from .prompts import (
    COMPLETION_DELIMITER,
    ENTITY_CONTINUE_EXTRACTION,
    ENTITY_EXTRACTION_SYSTEM,
    ENTITY_EXTRACTION_USER,
    TUPLE_DELIMITER,
)

logger = logging.getLogger(__name__)


class Extractor:
    def __init__(
        self,
        llm: LLMAdapter,
        *,
        gleaning_rounds: int = 0,
        max_concurrent: int = 5,
        max_tokens: int = 8000,
        cache: dict[str, str] | None = None,
    ) -> None:
        self._llm = llm
        self._gleaning_rounds = gleaning_rounds
        self._max_concurrent = max_concurrent
        self._max_tokens = max_tokens
        self._cache = cache

    async def aextract(self, chunk: Chunk) -> ExtractionResult:
        cache_key = self._cache_key(chunk)
        raw_text = self._cache.get(cache_key) if self._cache else None

        if raw_text is None:
            user = ENTITY_EXTRACTION_USER.replace("{input_text}", chunk.content)
            try:
                raw_text = await self._llm.acomplete(
                    ENTITY_EXTRACTION_SYSTEM,
                    user,
                    temperature=0.0,
                    max_tokens=self._max_tokens,
                )
            except Exception as exc:
                logger.error("LLM extraction call failed: %s", exc)
                raise

            for _ in range(self._gleaning_rounds):
                glean = await self._call_gleaning_async(chunk.content, raw_text)
                if glean:
                    raw_text += "\n" + glean

            if self._cache is not None:
                self._cache[cache_key] = raw_text
        else:
            logger.debug("Cache hit for chunk %s", chunk.id)

        nodes, edges = self._parse_extraction_result(raw_text, chunk)
        return ExtractionResult(nodes=nodes, edges=edges, chunk_id=chunk.id)

    async def aextract_batch(
        self,
        chunks: list[Chunk],
        *,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[ExtractionResult]:
        sem = asyncio.Semaphore(self._max_concurrent)
        done_count = 0
        lock = asyncio.Lock()

        async def _bounded(chunk: Chunk) -> ExtractionResult:
            nonlocal done_count
            async with sem:
                result = await self.aextract(chunk)
                async with lock:
                    done_count += 1
                    if progress_callback:
                        progress_callback(done_count, len(chunks))
                return result

        return list(await asyncio.gather(*[_bounded(c) for c in chunks]))

    def extract(self, chunk: Chunk) -> ExtractionResult:
        return asyncio.get_event_loop().run_until_complete(self.aextract(chunk))

    def extract_batch(self, chunks: list[Chunk]) -> list[ExtractionResult]:
        return asyncio.get_event_loop().run_until_complete(self.aextract_batch(chunks))

    async def _call_gleaning_async(self, content: str, first_result: str) -> str:
        user = ENTITY_EXTRACTION_USER.replace("{input_text}", content)
        gleaning_user = (
            f"---Previous extraction output---\n{first_result}\n\n"
            f"{ENTITY_CONTINUE_EXTRACTION}"
        )
        try:
            resp = await self._llm.acomplete(
                ENTITY_EXTRACTION_SYSTEM,
                f"{user}\n\n{gleaning_user}",
                temperature=0.0,
                max_tokens=self._max_tokens,
            )
            return resp
        except Exception as exc:
            logger.warning("Gleaning failed (non-fatal): %s", exc)
            return ""

    def _parse_extraction_result(
        self, raw_text: str, chunk: Chunk
    ) -> tuple[dict[str, list[RawNode]], dict[tuple[str, str], list[RawEdge]]]:
        maybe_nodes: dict[str, list[RawNode]] = defaultdict(list)
        maybe_edges: dict[tuple[str, str], list[RawEdge]] = defaultdict(list)

        text = raw_text.replace(COMPLETION_DELIMITER, "").replace(COMPLETION_DELIMITER.lower(), "")
        records = [line.strip() for line in text.split("\n") if line.strip()]

        for record in records:
            fields = [f.strip() for f in record.split(TUPLE_DELIMITER)]

            if len(fields) >= 4 and fields[0].lower() == "entity":
                name = self._sanitize(fields[1])
                entity_type = self._sanitize(fields[2]).replace(" ", "")
                description = fields[3].strip()
                if name and description:
                    node = RawNode(
                        name=name,
                        entity_type=entity_type,
                        description=description,
                        source_id=chunk.id,
                        file_path=chunk.file_path,
                    )
                    maybe_nodes[node.node_id].append(node)
                continue

            if len(fields) >= 5 and fields[0].lower() in ("relation", "relationship"):
                src = self._sanitize(fields[1])
                tgt = self._sanitize(fields[2])
                keywords = fields[3].strip()
                description = fields[4].strip()
                if src and tgt:
                    edge = RawEdge(
                        src=src,
                        tgt=tgt,
                        edge_type=self._infer_edge_type(keywords),
                        keywords=keywords,
                        description=description,
                        source_id=chunk.id,
                    )
                    maybe_edges[(edge.src.upper(), edge.tgt.upper())].append(edge)
                continue

            if record and not record.startswith("#"):
                logger.debug("Skipping unparseable line: %s", record[:100])

        return dict(maybe_nodes), dict(maybe_edges)

    @staticmethod
    def _sanitize(text: str) -> str:
        text = text.strip().strip("\"'`")
        return " ".join(text.split())

    @staticmethod
    def _infer_edge_type(keywords: str) -> str:
        kw = keywords.lower()
        mapping = {
            "belongs_to": "BELONGS_TO",
            "has_column": "HAS_COLUMN",
            "backed_by": "BACKED_BY",
            "refers_to": "REFERS_TO",
            "alias": "ALIAS_OF",
            "defined_as": "DEFINED_AS",
            "owned_by": "OWNED_BY",
            "joins": "JOINS_WITH",
            "part_of": "PART_OF",
        }
        for key, val in mapping.items():
            if key in kw:
                return val
        return "RELATED_TO"

    @staticmethod
    def _cache_key(chunk: Chunk) -> str:
        return hashlib.sha256(chunk.content.encode()).hexdigest()[:16]
