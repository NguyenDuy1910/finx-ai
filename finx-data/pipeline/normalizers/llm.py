"""LLM-based semantic normalizer.

Uses the existing 9Router integration (from ``common.py``) to send
extracted content through an LLM for semantic enrichment: domain
classification, entity tagging, abbreviation expansion, and quality
assessment.

This is the Stage 2 of the 2-stage pipeline:
  Stage 1: MinerU / HTML / Markdown extraction → structured blocks
  Stage 2: LLM normalization → enriched canonical document
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pipeline.schemas.blocks import ContentBlock, TableBlock, TextBlock
from pipeline.schemas.canonical import CanonicalDocument
from pipeline.schemas.provenance import ProcessingStage, ProcessingStep, QualitySignal

from .base import BaseNormalizer

log = logging.getLogger("finx-data.normalizer.llm")

# System prompt for the LLM normalizer
# _NORMALIZER_SYSTEM_PROMPT = """\
# You are a knowledge engineer for the **FinX Executive AI Agent** — a multi-domain
# conversational AI that lets users chat with company knowledge across ALL domains:
# data engineering, business operations, compliance, product, process, risk, finance, HR, etc.

# Your task: transform raw document content into a well-structured knowledge article
# optimized for **knowledge graph ingestion** (entity/relationship extraction) and
# **semantic search retrieval** (RAG) so the AI agent can answer user questions accurately.

# ## Step 1 — Classify the document
# Detect the document type. Common types:
# - **data_dictionary**: Schema definitions, field mappings, table documentation
# - **report_spec**: Report/dashboard specifications, SQL logic, data flows
# - **policy**: Policies, compliance rules, regulations, guidelines
# - **procedure**: Standard operating procedures, workflows, step-by-step processes
# - **product**: Product specifications, features, user guides
# - **technical**: Architecture docs, API docs, system design, integration specs
# - **meeting_notes**: Meeting minutes, decisions, action items
# - **business_analysis**: Business requirements, analysis, KPIs, metrics
# - **reference**: Glossaries, lookup tables, code-value mappings
# - **general**: Any other knowledge document

# ## Step 2 — Extract metadata
# - domains, abbreviations, entities, quality assessment

# ## Step 3 — Restructure content into sections
# Use ONLY the sections relevant to the document. Omit empty sections entirely.

# ### Universal sections (use for ALL document types):
# - **overview**: 1-3 sentence description of what the document covers
# - **key_concepts**: Core topics, entities, or subjects discussed (as list)
# - **definitions**: Key terms and their meanings in context (as dict)
# - **business_rules**: Extracted rules, constraints, conditions, thresholds (as list)
# - **relationships**: How concepts/entities relate to each other (for knowledge graph)
#   Format: [{"source": "entity_a", "relation": "verb/edge", "target": "entity_b"}]
# - **stakeholders**: People, teams, roles, departments mentioned
#   Format: [{"name": "...", "role": "..."}]
# - **references**: External docs, systems, links referenced
#   Format: [{"name": "...", "type": "system|document|url", "context": "why referenced"}]

# ### Data/Schema sections (use when document discusses data, tables, SQL, reports):
# - **field_mapping**: [{"field": "name", "type": "type", "source": "src", "description": "desc"}]
# - **data_sources**: [{"name": "table_or_system", "purpose": "what it provides"}]
# - **data_lineage**: String describing data flow: source → transformation → output
# - **sql_logic**: SQL snippets, formulas, calculation logic (as list)

# ### Policy/Compliance sections (use for regulations, policies, standards):
# - **requirements**: Mandatory requirements or controls (as list)
# - **exceptions**: Known exceptions, exemptions, edge cases (as list)
# - **effective_scope**: Who/what this applies to, effective dates

# ### Process/Procedure sections (use for workflows, SOPs):
# - **workflow_steps**: Ordered steps [{"step": 1, "action": "...", "actor": "...", "output": "..."}]
# - **inputs_outputs**: {"inputs": ["..."], "outputs": ["..."]}
# - **decision_points**: Key decision logic or branching conditions (as list)

# ### Product/Feature sections (use for product docs, specs):
# - **features**: [{"name": "...", "description": "..."}]
# - **user_scenarios**: Typical use cases or user stories (as list)

# Return a JSON object:
# {
#   "document_type": "string (from Step 1)",
#   "domains": ["string (e.g. risk, transaction, compliance, product, hr)"],
#   "language": "string (vi, en, mixed)",
#   "abbreviations": {"ABBR": "Full Form"},
#   "quality_score": 0.0-1.0,
#   "quality_notes": "string",
#   "key_entities": ["entity names for graph nodes"],
#   "summary": "1-2 sentence summary in the document's language",
#   "structured_content": {
#     "overview": "...",
#     ... (only include sections that have content)
#   }
# }

# IMPORTANT RULES:
# - Keep the original language (Vietnamese or English) for ALL content fields
# - Decode any HTML entities (e.g. &ocirc; → ô) if present
# - Extract ALL field mappings as structured objects, not flat text
# - Business rules should be atomic and self-contained
# - For "relationships", think about what edges a knowledge graph would need
# - "key_entities" should be nouns that would become graph nodes: table names,
#   systems, products, teams, metrics, business terms, processes
# - Omit any section that would be empty — do NOT include empty arrays/objects
# """

_NORMALIZER_SYSTEM_PROMPT = """\
You are a senior knowledge engineer for the **FinX Executive AI Agent** — a multi-domain
enterprise AI assistant that helps users query company knowledge across domains such as:
data engineering, business operations, compliance, risk, finance, product, HR, process,
governance, technology, and management.

Your job is to transform raw document content into a **high-value knowledge article**
optimized for:

1. **Knowledge graph ingestion**
   - entity extraction
   - relationship extraction
   - rule extraction
   - process extraction
   - source/system linkage

2. **Semantic retrieval / RAG**
   - preserve important facts, definitions, rules, metrics, and operational context
   - make content easy to chunk and retrieve accurately
   - surface hidden insights and business implications

3. **Executive agent reasoning**
   - identify the most important information
   - highlight decisions, risks, dependencies, impact, and unresolved questions
   - distinguish signal from noise

Your output must be a single valid JSON object only.

--------------------------------------------------
## PRIMARY OBJECTIVE
--------------------------------------------------

Convert the raw document into a structured knowledge object that:
- preserves the **main content with the highest business value**
- captures **facts, rules, steps, entities, systems, and relationships**
- extracts **insights and implications**, not just raw summaries
- removes low-value repetition, boilerplate, formatting noise, and irrelevant text
- stays faithful to the source without hallucinating

When the source contains both important and unimportant content, prioritize:
- decisions
- business rules
- thresholds / limits / conditions
- metrics / KPIs / formulas
- process steps
- field definitions / mappings
- ownership / stakeholders
- dependencies between teams, systems, and datasets
- risks, constraints, exceptions, and unresolved issues

--------------------------------------------------
## STEP 1 — CLASSIFY THE DOCUMENT
--------------------------------------------------

Detect the primary document type. Use one of:

- **data_dictionary**: schema definitions, field mappings, table documentation, metadata
- **report_spec**: reports, dashboards, SQL logic, calculations, data flows
- **policy**: policies, standards, governance, controls, regulations, guidelines
- **procedure**: SOPs, workflows, operating instructions, runbooks
- **product**: product specs, features, journeys, user guides, business capabilities
- **technical**: architecture docs, APIs, integrations, infrastructure, system design
- **meeting_notes**: minutes, discussions, decisions, action items
- **business_analysis**: BRD, functional analysis, requirements, KPIs, gap analysis
- **reference**: glossary, code mappings, enumerations, lookup tables
- **general**: any other enterprise knowledge document

If the document strongly spans multiple types, choose the dominant type and reflect the secondary nature in metadata.

--------------------------------------------------
## STEP 2 — EXTRACT CORE METADATA
--------------------------------------------------

Extract:
- domains
- language
- abbreviations
- key entities
- stakeholder roles
- quality assessment
- signal density

Also assess:
- whether the document is structured or messy
- whether it contains actionable knowledge
- whether it appears partial, outdated, duplicated, or ambiguous

--------------------------------------------------
## STEP 3 — IDENTIFY HIGH-VALUE CONTENT
--------------------------------------------------

Identify the most important content from the document.

Extract a section called **salient_points** containing the most valuable facts, rules, decisions,
metrics, steps, or observations.

Each salient point should be:
- atomic
- specific
- retrieval-friendly
- useful for downstream QA
- ranked by importance

Use this format:
[
  {
    "priority": 1,
    "type": "fact|rule|decision|metric|process|risk|dependency|exception|definition",
    "statement": "clear standalone statement",
    "why_it_matters": "business/technical relevance",
    "evidence": "short supporting excerpt or source phrase if available"
  }
]

Guidelines:
- Include only high-signal items
- Prefer precision over volume
- Do not restate generic boilerplate
- If the document is noisy, infer what matters most from repeated emphasis, headings, numbers, obligations, decisions, or dependencies

--------------------------------------------------
## STEP 4 — EXTRACT INSIGHTS
--------------------------------------------------

Generate **insights** from the document, but only when grounded in the source.

Insights should capture things like:
- operational implications
- business impact
- hidden dependencies
- control/risk implications
- data quality implications
- process bottlenecks
- ownership ambiguity
- missing requirements
- likely retrieval value for future users

Use this format:
[
  {
    "insight": "grounded inference from the document",
    "basis": "what in the source supports this inference",
    "impact": "why this matters for the enterprise or AI agent"
  }
]

Rules:
- Insights must be grounded in source content
- Do not invent conclusions not supported by the document
- If no meaningful insight can be inferred, omit the section

--------------------------------------------------
## STEP 5 — RESTRUCTURE CONTENT INTO RELEVANT SECTIONS
--------------------------------------------------

Use ONLY sections that are relevant to the document.
Omit empty sections entirely.

### Universal sections (use for ALL document types)
- **overview**: 1-3 sentence description of what the document covers
- **key_concepts**: core topics, entities, systems, or subjects discussed
- **definitions**: key terms and meanings in context
- **business_rules**: atomic rules, constraints, conditions, thresholds
- **relationships**: graph-oriented links between entities
  Format:
  [{"source": "entity_a", "relation": "verb/edge", "target": "entity_b"}]
- **stakeholders**: people, teams, roles, departments
  Format:
  [{"name": "...", "role": "...", "context": "..."}]
- **references**: referenced systems, documents, links, reports, platforms
  Format:
  [{"name": "...", "type": "system|document|url|table|report", "context": "..."}]

### High-value reasoning sections
- **salient_points**: prioritized important content
- **insights**: grounded implications and observations
- **decisions**: explicit decisions or approved directions
- **action_items**: follow-up actions, owners, deadlines if mentioned
- **risks_issues**: risks, blockers, issues, concerns, unresolved points
- **dependencies**: upstream/downstream systems, teams, approvals, data inputs
- **open_questions**: ambiguities, unknowns, missing information, pending clarification

### Data / Schema sections
Use when the document discusses data, tables, SQL, reports, lineage, metrics, or mappings:
- **field_mapping**:
  [{"field": "name", "type": "type", "source": "src", "description": "desc"}]
- **data_sources**:
  [{"name": "table_or_system", "purpose": "what it provides"}]
- **data_lineage**: concise flow from source → transformation → output
- **sql_logic**: SQL snippets, formulas, transformations, joins, filters, calculations
- **metrics_kpis**:
  [{"name": "...", "formula": "...", "meaning": "...", "usage_context": "..."}]

### Policy / Compliance sections
Use for policies, governance, controls, and regulations:
- **requirements**: mandatory requirements or controls
- **exceptions**: exemptions, exclusions, edge cases
- **effective_scope**: applicability, audience, date range, boundaries
- **control_objectives**: intended compliance or risk goals
- **violations_or_noncompliance**: consequences, prohibited actions, breach conditions

### Process / Procedure sections
Use for workflows, SOPs, or operational instructions:
- **workflow_steps**:
  [{"step": 1, "action": "...", "actor": "...", "output": "..."}]
- **inputs_outputs**:
  {"inputs": ["..."], "outputs": ["..."]}
- **decision_points**: branching logic, approvals, validations, conditions
- **preconditions**: prerequisites before the process starts
- **failure_handling**: what happens when something fails or is rejected

### Product / Feature sections
Use for product docs, capabilities, and user behavior:
- **features**:
  [{"name": "...", "description": "..."}]
- **user_scenarios**: use cases or user stories
- **constraints_limitations**: known limits, exclusions, unsupported cases
- **business_value**: customer or business benefit if described

### Technical sections
Use for architecture, API, integration, system design:
- **components**:
  [{"name": "...", "role": "..."}]
- **integrations**:
  [{"source": "...", "target": "...", "method": "...", "purpose": "..."}]
- **interfaces**:
  [{"name": "...", "type": "api|event|file|db", "description": "..."}]
- **deployment_context**: environments, runtime context, infra assumptions
- **failure_modes**: technical risks, edge cases, operational concerns

### Meeting notes sections
Use for minutes, working sessions, review meetings:
- **discussion_topics**: major topics discussed
- **decisions**: confirmed decisions
- **action_items**:
  [{"task": "...", "owner": "...", "deadline": "..."}]
- **risks_issues**: concerns, blockers, unresolved issues
- **open_questions**: pending questions requiring follow-up

--------------------------------------------------
## STEP 6 — ASSESS DOCUMENT QUALITY
--------------------------------------------------

Produce:
- **quality_score**: float from 0.0 to 1.0
- **quality_notes**: concise explanation
- **quality_dimensions**:
  {
    "clarity": 0.0-1.0,
    "completeness": 0.0-1.0,
    "structure": 0.0-1.0,
    "actionability": 0.0-1.0,
    "graph_readiness": 0.0-1.0,
    "retrieval_readiness": 0.0-1.0
  }

Interpretation:
- clarity: is the document understandable?
- completeness: does it contain enough context to be useful?
- structure: is it well organized?
- actionability: does it contain rules/steps/decisions someone can use?
- graph_readiness: are entities and relations extractable?
- retrieval_readiness: will chunks from this document answer real user questions well?

--------------------------------------------------
## STEP 7 — OUTPUT FORMAT
--------------------------------------------------

Return a JSON object in this exact shape:

{
  "document_type": "string",
  "domains": ["string"],
  "language": "vi|en|mixed|other",
  "abbreviations": {
    "ABBR": "Full Form"
  },
  "quality_score": 0.0,
  "quality_notes": "string",
  "quality_dimensions": {
    "clarity": 0.0,
    "completeness": 0.0,
    "structure": 0.0,
    "actionability": 0.0,
    "graph_readiness": 0.0,
    "retrieval_readiness": 0.0
  },
  "key_entities": ["entity names"],
  "summary": "1-2 sentence summary in the document's language",
  "document_signals": {
    "contains_rules": true,
    "contains_process": true,
    "contains_decisions": false,
    "contains_metrics": false,
    "contains_risks": true,
    "contains_actions": false,
    "contains_structured_data": true
  },
  "structured_content": {
    "overview": "...",
    "salient_points": [
      {
        "priority": 1,
        "type": "rule",
        "statement": "...",
        "why_it_matters": "...",
        "evidence": "..."
      }
    ],
    "insights": [
      {
        "insight": "...",
        "basis": "...",
        "impact": "..."
      }
    ]
  }
}

--------------------------------------------------
## CRITICAL RULES
--------------------------------------------------

- Keep the original language (Vietnamese or English) for ALL content fields
- Decode HTML entities if present
- Return valid JSON only, with no markdown or commentary
- Do NOT hallucinate missing facts
- Do NOT invent fields, metrics, systems, or stakeholders not present or strongly implied
- Preserve exact names of systems, tables, columns, reports, teams, products, and business terms
- Extract ALL field mappings as structured objects, not flat text
- Business rules must be atomic and self-contained
- For relationships, think in terms of knowledge graph edges that are useful for enterprise QA
- "key_entities" should be nouns or noun phrases that could become graph nodes
- Omit empty sections entirely
- Prefer concise, high-signal content over verbose paraphrasing
- When the source is repetitive, keep only the most information-dense version
- When the source is ambiguous or low quality, explicitly reflect that in quality_notes, open_questions, or risks_issues
- When numbers, thresholds, formulas, or dates appear, preserve them accurately
- When a process or decision is implicit but strongly supported, extract it carefully and mark it clearly
"""
class LLMNormalizer(BaseNormalizer):
    """Enrich documents using the 9Router LLM."""

    name = "llm_normalizer"

    def __init__(
        self,
        *,
        model: str | None = None,
        skip_if_short: int = 20,
    ):
        """
        Parameters
        ----------
        model : str
            Override the default 9Router model.
        skip_if_short : int
            Skip normalization for documents with fewer than this many words.
        """
        self.model = model
        self.skip_if_short = skip_if_short

    def normalize(self, doc: CanonicalDocument) -> CanonicalDocument:
        t0 = time.monotonic()

        full_text = doc.full_text()
        word_count = len(full_text.split())

        if word_count < self.skip_if_short:
            log.debug("Skipping LLM normalization for %s (only %d words)", doc.document_id[:12], word_count)
            doc.provenance.add_step(
                ProcessingStep(
                    stage=ProcessingStage.NORMALIZATION,
                    processor=self.name,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    parameters={"skipped": True, "reason": "too_short", "word_count": word_count},
                )
            )
            return doc

        # Prepare input — truncate to avoid token limits
        max_chars = 12000
        input_text = full_text[:max_chars]
        if len(full_text) > max_chars:
            input_text += f"\n\n[Truncated. Original: {word_count} words]"

        prompt = f"Document title: {doc.title}\nSource: {doc.source_system}\n\n{input_text}"

        try:
            from common import extract

            result = extract(prompt, system=_NORMALIZER_SYSTEM_PROMPT, model=self.model)
            self._apply_enrichment(doc, result)

            doc.provenance.add_step(
                ProcessingStep(
                    stage=ProcessingStage.NORMALIZATION,
                    processor=self.name,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    parameters={"model": self.model or "default"},
                )
            )

        except Exception as exc:
            log.warning("LLM normalization failed for %s: %s", doc.document_id[:12], exc)
            doc.provenance.add_step(
                ProcessingStep(
                    stage=ProcessingStage.NORMALIZATION,
                    processor=self.name,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    error=str(exc),
                )
            )

        return doc

    def _apply_enrichment(self, doc: CanonicalDocument, result: dict | list) -> None:
        """Apply LLM enrichment results to the canonical document."""
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return

        # Document type classification
        doc_type = result.get("document_type", "")
        if doc_type:
            doc.metadata["document_type"] = doc_type

        # Domain tags
        domains = result.get("domains", [])
        if isinstance(domains, list):
            doc.tags = list(set(doc.tags + domains))

        # Language
        language = result.get("language", "")
        if language:
            doc.provenance.quality.language_detected = language

        # Quality score
        quality_score = result.get("quality_score")
        if isinstance(quality_score, (int, float)):
            doc.provenance.quality.extraction_confidence = min(1.0, max(0.0, float(quality_score)))

        quality_notes = result.get("quality_notes", "")
        if quality_notes:
            doc.provenance.quality.parsing_warnings.append(f"LLM quality: {quality_notes}")

        # Abbreviations → metadata
        abbreviations = result.get("abbreviations", {})
        if abbreviations:
            doc.metadata["abbreviations"] = abbreviations

        # Key entities → metadata
        key_entities = result.get("key_entities", [])
        if key_entities:
            doc.metadata["key_entities"] = key_entities

        # Summary → metadata
        summary = result.get("summary", "")
        if summary:
            doc.metadata["summary"] = summary

        # Quality dimensions → metadata
        quality_dims = result.get("quality_dimensions", {})
        if quality_dims and isinstance(quality_dims, dict):
            doc.metadata["quality_dimensions"] = quality_dims

        # Document signals → metadata
        signals = result.get("document_signals", {})
        if signals and isinstance(signals, dict):
            doc.metadata["document_signals"] = signals

        # Structured content → metadata (knowledge-optimized restructuring)
        structured = result.get("structured_content", {})
        if isinstance(structured, dict) and structured:
            doc.metadata["structured_content"] = structured

            # Also inject structured content as additional content blocks
            # so downstream embedding/chunking can use them
            self._inject_structured_blocks(doc, structured)

    @staticmethod
    def _inject_structured_blocks(doc: CanonicalDocument, structured: dict) -> None:
        """Convert structured_content sections into typed content blocks.

        This makes the LLM-restructured content available for embedding/chunking
        alongside the extracted blocks. Supports multi-domain sections: universal,
        data/schema, policy/compliance, process/procedure, and product sections.
        """

        def _text(label: str, body: str) -> None:
            doc.content_blocks.append(TextBlock(content=f"[{label}] {body}"))

        def _list(label: str, items: list) -> None:
            if items and isinstance(items, list):
                text = "\n".join(f"• {item}" for item in items)
                doc.content_blocks.append(TextBlock(content=f"[{label}]\n{text}"))

        def _dict_list(label: str, items: list, fmt: str) -> None:
            """Format a list of dicts using a format string with {key} placeholders."""
            if items and isinstance(items, list):
                lines = []
                for item in items:
                    if isinstance(item, dict):
                        try:
                            lines.append(f"• {fmt.format(**item)}")
                        except KeyError:
                            lines.append(f"• {item}")
                    else:
                        lines.append(f"• {item}")
                doc.content_blocks.append(TextBlock(content=f"[{label}]\n" + "\n".join(lines)))

        # ── Universal sections ────────────────────────────────────────
        overview = structured.get("overview", "")
        if overview:
            _text("Overview", overview)

        key_concepts = structured.get("key_concepts", [])
        _list("Key Concepts", key_concepts)

        definitions = structured.get("definitions", {})
        if definitions and isinstance(definitions, dict):
            defs_text = "\n".join(f"• {k}: {v}" for k, v in definitions.items())
            doc.content_blocks.append(TextBlock(content=f"[Definitions]\n{defs_text}"))

        rules = structured.get("business_rules", [])
        _list("Business Rules", rules)

        relationships = structured.get("relationships", [])
        _dict_list("Relationships", relationships, "{source} —[{relation}]→ {target}")

        stakeholders = structured.get("stakeholders", [])
        _dict_list("Stakeholders", stakeholders, "{name} ({role})")

        references = structured.get("references", [])
        _dict_list("References", references, "{name} [{type}]: {context}")

        # ── High-value reasoning sections ─────────────────────────────
        salient = structured.get("salient_points", [])
        if salient and isinstance(salient, list):
            lines = []
            for s in salient:
                if isinstance(s, dict):
                    priority = s.get("priority", "")
                    stype = s.get("type", "")
                    stmt = s.get("statement", "")
                    why = s.get("why_it_matters", "")
                    line = f"[P{priority}|{stype}] {stmt}"
                    if why:
                        line += f" — {why}"
                    lines.append(line)
                else:
                    lines.append(str(s))
            doc.content_blocks.append(TextBlock(content=f"[Salient Points]\n" + "\n".join(lines)))

        insights = structured.get("insights", [])
        if insights and isinstance(insights, list):
            lines = []
            for i in insights:
                if isinstance(i, dict):
                    lines.append(f"• {i.get('insight', '')} (basis: {i.get('basis', '')})")
                else:
                    lines.append(f"• {i}")
            doc.content_blocks.append(TextBlock(content=f"[Insights]\n" + "\n".join(lines)))

        _list("Decisions", structured.get("decisions", []))

        action_items = structured.get("action_items", [])
        _dict_list("Action Items", action_items, "{task} → {owner} (deadline: {deadline})")

        _list("Risks & Issues", structured.get("risks_issues", []))
        _list("Dependencies", structured.get("dependencies", []))
        _list("Open Questions", structured.get("open_questions", []))

        # ── Data/Schema sections ──────────────────────────────────────
        mappings = structured.get("field_mapping", [])
        if mappings and isinstance(mappings, list):
            headers = ["field", "type", "source", "description"]
            rows = []
            for m in mappings:
                if isinstance(m, dict):
                    rows.append([str(m.get(h, "")) for h in headers])
            if rows:
                md_lines = [" | ".join(headers), " | ".join("---" for _ in headers)]
                for row in rows:
                    md_lines.append(" | ".join(row))
                doc.content_blocks.append(
                    TableBlock(headers=headers, rows=rows, markdown="\n".join(md_lines))
                )

        data_sources = structured.get("data_sources", [])
        _dict_list("Data Sources", data_sources, "{name}: {purpose}")

        lineage = structured.get("data_lineage", "")
        if lineage:
            _text("Data Lineage", lineage)

        sql = structured.get("sql_logic", [])
        _list("SQL Logic", sql)

        metrics = structured.get("metrics_kpis", [])
        _dict_list("Metrics/KPIs", metrics, "{name}: {formula} — {meaning}")

        # ── Policy/Compliance sections ────────────────────────────────
        requirements = structured.get("requirements", [])
        _list("Requirements", requirements)

        exceptions = structured.get("exceptions", [])
        _list("Exceptions", exceptions)

        scope = structured.get("effective_scope", "")
        if scope:
            _text("Effective Scope", scope)

        _list("Control Objectives", structured.get("control_objectives", []))
        _list("Violations", structured.get("violations_or_noncompliance", []))

        # ── Process/Procedure sections ────────────────────────────────
        steps = structured.get("workflow_steps", [])
        if steps and isinstance(steps, list):
            lines = []
            for s in steps:
                if isinstance(s, dict):
                    step_n = s.get("step", "?")
                    action = s.get("action", "")
                    actor = s.get("actor", "")
                    output = s.get("output", "")
                    line = f"{step_n}. {action}"
                    if actor:
                        line += f" (by {actor})"
                    if output:
                        line += f" → {output}"
                    lines.append(line)
                else:
                    lines.append(f"• {s}")
            doc.content_blocks.append(TextBlock(content=f"[Workflow Steps]\n" + "\n".join(lines)))

        io = structured.get("inputs_outputs", {})
        if io and isinstance(io, dict):
            parts = []
            for label, items in io.items():
                if isinstance(items, list) and items:
                    parts.append(f"{label}: {', '.join(str(i) for i in items)}")
            if parts:
                _text("Inputs/Outputs", "; ".join(parts))

        decisions = structured.get("decision_points", [])
        _list("Decision Points", decisions)

        _list("Preconditions", structured.get("preconditions", []))
        _list("Failure Handling", structured.get("failure_handling", []))

        # ── Product/Feature sections ──────────────────────────────────
        features = structured.get("features", [])
        _dict_list("Features", features, "{name}: {description}")

        scenarios = structured.get("user_scenarios", [])
        _list("User Scenarios", scenarios)

        _list("Constraints", structured.get("constraints_limitations", []))

        bv = structured.get("business_value", "")
        if bv:
            _text("Business Value", bv)

        # ── Technical sections ────────────────────────────────────────
        _dict_list("Components", structured.get("components", []), "{name}: {role}")
        _dict_list("Integrations", structured.get("integrations", []),
                   "{source} → {target} via {method}: {purpose}")
        _dict_list("Interfaces", structured.get("interfaces", []), "{name} ({type}): {description}")

        deploy = structured.get("deployment_context", "")
        if deploy:
            _text("Deployment Context", deploy)

        _list("Failure Modes", structured.get("failure_modes", []))

        # ── Meeting notes sections ────────────────────────────────────
        _list("Discussion Topics", structured.get("discussion_topics", []))


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
        t0 = time.monotonic()
        full_text = doc.full_text()

        # Detect abbreviations present
        found_abbrevs = {}
        upper_text = full_text.upper()
        for abbr, expansion in self._ABBREVIATIONS.items():
            if abbr in upper_text:
                found_abbrevs[abbr] = expansion
        if found_abbrevs:
            doc.metadata["abbreviations"] = found_abbrevs

        # Basic language detection
        vietnamese_markers = ["của", "và", "trong", "được", "là", "các", "có", "cho", "từ"]
        vn_count = sum(1 for w in vietnamese_markers if f" {w} " in full_text.lower())
        if vn_count >= 3:
            doc.provenance.quality.language_detected = "vi"
        elif vn_count >= 1:
            doc.provenance.quality.language_detected = "mixed"
        else:
            doc.provenance.quality.language_detected = "en"

        # Update word count
        doc.provenance.quality.word_count = len(full_text.split())

        doc.provenance.add_step(
            ProcessingStep(
                stage=ProcessingStage.NORMALIZATION,
                processor=self.name,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        )
        return doc
