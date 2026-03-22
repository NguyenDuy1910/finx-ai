"""LLM-based normalizer — chunk-pipeline aligned.

Enriches CanonicalDocument metadata that flows into ChunkDocument fields
during the chunking stage.  The LLM extracts *document-level* signals that
every chunk inherits:

    LLM output key       → doc.metadata key   → ChunkDocument field
    ───────────────────── ─────────────────── ─────────────────────
    document_type         document_type         doc_type
    language              language              language
    domains               domains               domains
    summary               summary               summary
    key_entities          key_entities          keywords
    keywords              keywords              keywords (merged)
    abbreviations         abbreviations         acronym_expansions
    quality_score         quality_score         quality_score

Content blocks are NOT modified — chunkers work with the original
extracted content only.
"""

from __future__ import annotations

import logging

from pipeline.schemas.canonical import CanonicalDocument

from .base import BaseNormalizer

log = logging.getLogger("finx-data.normalizer.llm")


# ---------------------------------------------------------------------------
# System prompt — focused on metadata the chunk pipeline actually consumes
# ---------------------------------------------------------------------------
_NORMALIZER_SYSTEM_PROMPT = """\
You are a knowledge engineer for the FinX Enterprise AI Agent.
Analyse the document and return a single JSON object with these fields:

1. **document_type** (string) — one of:
   data_dictionary, report_spec, policy, procedure, product, technical,
   meeting_notes, business_analysis, reference, general

2. **language** (string) — "vi", "en", "mixed", or ISO-639-1 code

3. **domains** (list[str]) — business domains the document belongs to.
   Examples: data_engineering, compliance, risk, finance, operations,
   product, hr, technology, governance, management

4. **summary** (string) — 1-3 sentence summary in the document's own language.
   Capture the core purpose, scope, and key conclusions.

5. **key_entities** (list[str]) — important named entities: systems, teams,
   products, regulations, metrics, tables, APIs.  These become searchable
   keywords for every chunk of this document.

6. **keywords** (list[str]) — additional retrieval-friendly terms and phrases
   that a user might search for.  Include synonyms, Vietnamese/English
   equivalents, and domain jargon.

7. **abbreviations** (object) — map of acronyms → full expansions found in
   the document.  Example: {"NPL": "Non-Performing Loan", "CAR": "Capital Adequacy Ratio"}

8. **quality_score** (float 0.0-1.0) — overall document quality for RAG:
   - 0.0-0.3: noisy / low-value / boilerplate
   - 0.4-0.6: average, partial content
   - 0.7-0.9: good, structured, actionable
   - 1.0: excellent reference material

Rules:
- Return valid JSON only, no markdown, no commentary.
- Keep the original language for summary and keywords.
- Do NOT hallucinate entities, systems, or facts not in the source.
- Preserve exact names of systems, tables, columns, reports, teams, products.
- Omit keys whose value would be empty ([], {}, "", null).
"""


class LLMNormalizer(BaseNormalizer):
    """Enrich CanonicalDocument metadata via 9Router LLM.

    Only sets metadata keys that ``BaseChunker._base_chunk_doc()`` actually
    reads.  Content blocks are never modified — chunkers work with the
    original extracted content only.
    """

    name = "llm_normalizer"

    def __init__(
        self,
        *,
        model: str | None = None,
        skip_if_short: int = 20,
    ):
        self.model = model
        self.skip_if_short = skip_if_short

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def normalize(self, doc: CanonicalDocument) -> CanonicalDocument:
        full_text = doc.full_text()
        word_count = len(full_text.split())

        if word_count < self.skip_if_short:
            log.debug("Skipping LLM normalization for %s (only %d words)",
                      doc.document_id[:12], word_count)
            return doc

        max_chars = 12_000
        input_text = full_text[:max_chars]
        if len(full_text) > max_chars:
            input_text += f"\n\n[Truncated. Original: {word_count} words]"

        prompt = (
            f"Document title: {doc.title}\n"
            f"Source: {doc.source_system}\n\n"
            f"{input_text}"
        )

        try:
            result = self._call_llm(prompt, model=self.model)
            self._apply_enrichment(doc, result)
        except Exception as exc:
            log.warning("LLM normalization failed for %s: %s",
                        doc.document_id[:12], exc)

        return doc

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    @staticmethod
    def _call_llm(prompt: str, model: str | None = None) -> dict:
        """Call 9Router LLM for structured JSON extraction."""
        import json as _json
        import os

        from openai import OpenAI

        base_url = os.environ.get("NINE_ROUTER_BASE_URL", "http://localhost:20128/v1")
        api_key = os.environ.get("NINE_ROUTER_API_KEY", "YOUR_9ROUTER_KEY")
        default_model = os.environ.get("NINE_ROUTER_MODEL", "default")

        client = OpenAI(base_url=base_url, api_key=api_key)
        resp = client.chat.completions.create(
            model=model or default_model,
            messages=[
                {"role": "system", "content": _NORMALIZER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        return _json.loads(raw)

    # ------------------------------------------------------------------
    # Apply enrichment → doc.metadata  (consumed by chunkers)
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_enrichment(doc: CanonicalDocument, result: dict | list) -> None:
        """Map LLM output to metadata keys that chunkers read.

        Mapping (LLM key → metadata key → ChunkDocument field):
            document_type  → document_type  → doc_type
            language       → language       → language
            domains        → domains        → domains  (+ merged into tags)
            summary        → summary        → summary
            key_entities   → key_entities   → keywords
            keywords       → key_entities   → keywords  (merged)
            abbreviations  → abbreviations  → acronym_expansions
            quality_score  → quality_score  → quality_score
        """
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return

        meta = doc.metadata

        # document_type → doc_type
        if doc_type := result.get("document_type", ""):
            meta["document_type"] = doc_type

        # language
        if language := result.get("language", ""):
            meta["language"] = language

        # domains → metadata["domains"]  AND  merged into doc.tags
        domains = result.get("domains", [])
        if isinstance(domains, list) and domains:
            meta["domains"] = domains
            doc.tags = list(set(doc.tags + domains))

        # summary
        if summary := result.get("summary", ""):
            meta["summary"] = summary

        # key_entities + keywords → merged list in metadata["key_entities"]
        key_entities = result.get("key_entities", [])
        keywords = result.get("keywords", [])
        merged = list(dict.fromkeys(
            (key_entities if isinstance(key_entities, list) else [])
            + (keywords if isinstance(keywords, list) else [])
        ))
        if merged:
            meta["key_entities"] = merged

        # abbreviations → acronym_expansions
        abbreviations = result.get("abbreviations", {})
        if isinstance(abbreviations, dict) and abbreviations:
            meta["abbreviations"] = abbreviations

        # quality_score
        quality_score = result.get("quality_score")
        if isinstance(quality_score, (int, float)):
            meta["quality_score"] = min(1.0, max(0.0, float(quality_score)))


class RuleBasedNormalizer(BaseNormalizer):
    """Apply deterministic normalization rules without LLM calls.

    Useful for fast processing or when LLM is unavailable. Handles:
    - Banking abbreviation detection
    - Basic language detection
    - Word count / quality signals
    """

    name = "rule_normalizer"

    # Common Vietnamese banking abbreviations
    _ABBREVIATIONS = {
        "NPL": "Non-Performing Loan",
        "CASA": "Current Account Savings Account",
        "NIM": "Net Interest Margin",
        "NII": "Net Interest Income",
        "CAR": "Capital Adequacy Ratio",
        "LDR": "Loan-to-Deposit Ratio",
        "ECL": "Expected Credit Loss",
        "PD": "Probability of Default",
        "LGD": "Loss Given Default",
        "EAD": "Exposure at Default",
        "CIF": "Customer Information File",
        "KYC": "Know Your Customer",
        "AML": "Anti-Money Laundering",
        "PAN": "Primary Account Number",
        "DPD": "Days Past Due",
        "MOB": "Month on Book",
        "RWA": "Risk-Weighted Assets",
        "SBV": "State Bank of Vietnam",
        "NAPAS": "National Payment Corporation of Vietnam",
    }

    def normalize(self, doc: CanonicalDocument) -> CanonicalDocument:
        full_text = doc.full_text()

        found_abbrevs = {}
        upper_text = full_text.upper()
        for abbr, expansion in self._ABBREVIATIONS.items():
            if abbr in upper_text:
                found_abbrevs[abbr] = expansion
        if found_abbrevs:
            doc.metadata["abbreviations"] = found_abbrevs

        vietnamese_markers = ["của", "và", "trong", "được", "là", "các", "có", "cho", "từ"]
        vn_count = sum(1 for w in vietnamese_markers if f" {w} " in full_text.lower())
        if vn_count >= 3:
            doc.metadata["language"] = "vi"
        elif vn_count >= 1:
            doc.metadata["language"] = "mixed"
        else:
            doc.metadata["language"] = "en"

        return doc
