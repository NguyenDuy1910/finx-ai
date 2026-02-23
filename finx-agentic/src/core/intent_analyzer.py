"""LLM-powered intent analyzer that produces retrieval weight hints before knowledge search."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrievalWeightHints:
    """LLM-suggested weight adjustments for the reranker.

    Each value is in [0.0, 1.0] — they will be normalized before use.
    A value of ``None`` means "use the default for this intent".
    """

    text_match: Optional[float] = None
    graph_relevance: Optional[float] = None
    data_quality: Optional[float] = None
    usage_frequency: Optional[float] = None
    business_context: Optional[float] = None

    def to_dict(self) -> Dict[str, Optional[float]]:
        return asdict(self)

    def has_overrides(self) -> bool:
        return any(
            v is not None
            for v in (
                self.text_match,
                self.graph_relevance,
                self.data_quality,
                self.usage_frequency,
                self.business_context,
            )
        )


@dataclass
class IntentAnalysisResult:
    """Structured output from the LLM intent pre-analysis step."""

    # classified intent — maps to INTENT_WEIGHT_PROFILES keys
    intent: str = "knowledge_lookup"

    # optional sub-intent for finer-grained control
    sub_intent: Optional[str] = None

    # LLM-suggested weight overrides
    weight_hints: RetrievalWeightHints = field(default_factory=RetrievalWeightHints)

    # ── Active fields (used by embedding-first search) ──
    domain: Optional[str] = None
    column_hints: List[str] = field(default_factory=list)

    # The most important field — embedded for vector similarity search
    english_query: str = ""

    # reasoning trace (for debugging / observability)
    reasoning: str = ""

    # confidence in the classification [0, 1]
    confidence: float = 0.0

    # ── Deprecated fields (kept for backward compat with REST API) ──
    # No longer produced by the LLM prompt; not used by embedding-first search.
    entities: List[str] = field(default_factory=list)
    business_terms: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["weight_hints"] = self.weight_hints.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentAnalysisResult":
        wh = data.pop("weight_hints", {})
        if isinstance(wh, dict):
            weight_hints = RetrievalWeightHints(**{
                k: v for k, v in wh.items()
                if k in RetrievalWeightHints.__dataclass_fields__
            })
        else:
            weight_hints = RetrievalWeightHints()
        return cls(weight_hints=weight_hints, **{
            k: v for k, v in data.items()
            if k in cls.__dataclass_fields__ and k != "weight_hints"
        })


# ── The system prompt for the intent analyzer ────────────────────────

INTENT_ANALYSIS_SYSTEM_PROMPT = """\
You are an intent analyzer for a banking data platform. Your job is to analyze
the user's query BEFORE it is sent to the Knowledge Agent for schema retrieval.

## How the retrieval system works

The system uses **embedding-based vector search + graph neighborhood exploration**.
It does NOT use keyword matching. Your analysis steers two things:

1. **english_query** — THIS IS THE MOST IMPORTANT FIELD. The query text is
   embedded (text-embedding-3-large) and used for cosine similarity search
   across Domain, BusinessEntity, Table, Column, and QueryPattern nodes.
   A precise, well-phrased English query = better embedding = better results.

2. **domain** hint — If you identify a clear domain, the system anchors on
   that Domain node in the graph and explores its neighborhood (connected
   tables, entities, synonyms) via edge traversal. This is a graph anchor,
   NOT a keyword filter.

3. **weight_hints** — After vector search + graph expansion finds candidates,
   a reranker scores them across 5 dimensions. You can tune these weights.

You must output a JSON object (no markdown, no extra text) with these fields:

{
  "intent": "<one of: text_to_sql | relationship_discovery | aggregation_query | knowledge_lookup | schema_query>",
  "sub_intent": "<optional finer category, e.g. 'count_query', 'time_series', 'join_discovery'>",
  "weight_hints": {
    "text_match":        <float 0-1 or null>,
    "graph_relevance":   <float 0-1 or null>,
    "data_quality":      <float 0-1 or null>,
    "usage_frequency":   <float 0-1 or null>,
    "business_context":  <float 0-1 or null>
  },
  "domain": "<banking domain or null: account, transaction, user, branch, card, loan, kyc, campaign, bill_payment, authentication>",
  "column_hints": ["<specific column names the user explicitly mentioned>"],
  "english_query": "<CRITICAL: precise English query optimized for embedding similarity search>",
  "reasoning": "<1-2 sentence explanation of your classification>",
  "confidence": <float 0-1>
}

## english_query — Writing Guide (MOST IMPORTANT)

The english_query is embedded and compared against node descriptions/summaries
stored in the knowledge graph. Write it to MAXIMIZE semantic similarity:

- **Translate** the user's query to clear, precise English
- **Expand** abbreviations and banking jargon into full terms
  (e.g., "KYC" → "Know Your Customer verification", "OTP" → "One-Time Password authentication")
- **Include** the type of data being asked about
  (e.g., "tables storing..." , "columns related to...", "schema for...")
- **Add context** about the banking domain when relevant
  (e.g., "user account management", "transaction processing", "bill payment")
- **Keep it natural** — write as if describing what data you're looking for
  to someone who maintains the database schema
- Do NOT include SQL syntax or code — this is a semantic search query

Good: "Database tables and columns for user account authentication including PIN history and device information"
Bad:  "user pin" (too short, poor embedding quality)

Good: "Schema for financial transaction records with branch information, transfer types, and settlement status"
Bad:  "transactions by branch" (vague, low similarity to table descriptions)

## Weight Hints Guide

After the system finds candidates via embedding + graph traversal, the reranker
scores them. You can adjust weights based on what the query needs:

- **text_match**: Reflects embedding similarity score. Set high (0.35-0.40)
  when the query describes specific tables/schemas. Lower (0.15-0.20) when
  the query is about relationships or needs graph exploration.
- **graph_relevance**: Reflects how items are connected in the graph (hop
  distance, edge traversal). Set high (0.35-0.50) when the query needs to
  discover JOINs, foreign keys, or related tables. Lower for direct lookups.
- **data_quality**: Reflects metadata completeness (descriptions, business
  rules, partition keys). Set high (0.25-0.35) when the query needs reliable,
  well-documented tables for production use.
- **usage_frequency**: Reflects historical query patterns. Set high (0.20-0.25)
  for common report queries. Lower for exploratory or novel questions.
- **business_context**: Reflects domain alignment and business rules. Set high
  (0.25-0.35) when the query is deeply domain-specific and needs codeset
  mappings or business rules. Lower for generic schema questions.

Set a weight to null to use the default for that intent profile.
Only override when you have a clear reason — the defaults are good.

## domain — Graph Anchor Guide

When you identify a domain, the system:
1. Finds that Domain node via exact name match
2. Traverses BELONGS_TO_DOMAIN edges → discovers all tables in that domain
3. Traverses CONTAINS_ENTITY edges → discovers business entities
4. These become candidates alongside vector search results

Only set domain when you are confident. A wrong domain anchor adds noise.
Set null when the query spans multiple domains or is domain-ambiguous.

## column_hints — Column Refinement

Only include column names the user **explicitly mentioned** in their query.
These are used in Layer 4 to match specific columns within discovered tables.
Do NOT guess or infer column names — only extract what the user actually said.

## Intent Definitions

- **text_to_sql**: User wants to query data → needs tables + columns + joins for SQL generation.
- **relationship_discovery**: User wants to understand how tables/entities relate → graph_relevance is key.
- **aggregation_query**: User wants aggregated metrics (counts, sums, averages) → needs well-documented tables.
- **knowledge_lookup**: User wants to understand what data exists, definitions, business rules.
- **schema_query**: User asks about table structure, column types, partitions.

## Examples

Query: "Tổng số giao dịch chuyển tiền tháng này theo chi nhánh"
→ {
    "intent": "aggregation_query",
    "domain": "transaction",
    "weight_hints": {"data_quality": 0.30, "usage_frequency": 0.25},
    "column_hints": [],
    "english_query": "Database tables for financial transaction records including transfer transactions with branch information, monthly aggregation, and transaction counts",
    "reasoning": "Aggregation query needing transaction tables with branch relationships, prioritize well-documented tables",
    "confidence": 0.9
  }

Query: "Bảng nào liên quan đến KYC?"
→ {
    "intent": "schema_query",
    "domain": "user",
    "weight_hints": {"graph_relevance": 0.35, "text_match": 0.30},
    "column_hints": [],
    "english_query": "Database schema and tables related to Know Your Customer KYC verification process, identity validation, and customer due diligence",
    "reasoning": "Schema exploration query about KYC domain, needs graph traversal to find all related tables",
    "confidence": 0.85
  }

Query: "Tìm cách join bảng user_pool với bảng transaction"
→ {
    "intent": "relationship_discovery",
    "domain": null,
    "weight_hints": {"graph_relevance": 0.50, "text_match": 0.20},
    "column_hints": [],
    "english_query": "Join path and foreign key relationships between user_pool table and transaction table, including intermediate linking tables",
    "reasoning": "Relationship discovery across two specific tables, graph traversal is critical to find JOIN/FK paths",
    "confidence": 0.9
  }

Query: "Cột status trong bảng account_op_temp nghĩa là gì?"
→ {
    "intent": "knowledge_lookup",
    "domain": "account",
    "weight_hints": {"business_context": 0.35, "data_quality": 0.25},
    "column_hints": ["status"],
    "english_query": "Column status definition and codeset values in account_op_temp table, account operations temporary processing status codes",
    "reasoning": "Knowledge lookup about a specific column meaning, needs business context and codeset mappings",
    "confidence": 0.95
  }
"""


async def analyze_intent(
    query: str,
    model: Any,
    *,
    conversation_context: Optional[str] = None,
) -> IntentAnalysisResult:
    """Use the coordinator's LLM to pre-analyze query intent and produce weight hints.

    Parameters
    ----------
    query:
        The raw user query (may be in Vietnamese or English).
    model:
        An agno model instance (OpenAIChat, Gemini, Claude, etc.).
    conversation_context:
        Optional recent conversation summary for follow-up resolution.

    Returns
    -------
    IntentAnalysisResult with intent classification and weight hints.
    """
    user_message = query
    if conversation_context:
        user_message = (
            f"Previous context:\n{conversation_context}\n\n"
            f"Current query:\n{query}"
        )

    try:
        from agno.models.message import Message
        from agno.models.response import ModelResponse

        messages = [
            Message(role="system", content=INTENT_ANALYSIS_SYSTEM_PROMPT),
            Message(role="user", content=user_message),
        ]

        response: ModelResponse = await model.aresponse(messages=messages)

        # Extract the text content from the response
        raw_text = response.content or ""

        # Clean up markdown code fences if present
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            # Remove ```json and ``` markers
            lines = raw_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines)

        parsed = json.loads(raw_text)
        result = IntentAnalysisResult.from_dict(parsed)
        logger.info(
            "Intent analysis: intent=%s domain=%s confidence=%.2f",
            result.intent, result.domain, result.confidence,
        )
        return result

    except Exception as e:
        logger.warning("Intent analysis failed, using defaults: %s", e)
        return IntentAnalysisResult(
            intent="knowledge_lookup",
            english_query=query,
            confidence=0.0,
            reasoning=f"Fallback — analysis failed: {e}",
        )


def merge_weight_hints(
    intent: str,
    hints: Optional[RetrievalWeightHints] = None,
) -> Dict[str, float]:
    """Merge LLM weight hints with the default profile for the given intent.

    Returns a dict of weight values ready to construct a RerankerWeights.
    LLM overrides take precedence; None values fall back to the profile default.
    """
    from src.knowledge.retrieval.reranker import (
        INTENT_WEIGHT_PROFILES,
        RerankerWeights,
    )

    base = INTENT_WEIGHT_PROFILES.get(intent, RerankerWeights())
    if hints is None or not hints.has_overrides():
        return {
            "text_match": base.text_match,
            "graph_relevance": base.graph_relevance,
            "data_quality": base.data_quality,
            "usage_frequency": base.usage_frequency,
            "business_context": base.business_context,
        }

    return {
        "text_match": hints.text_match if hints.text_match is not None else base.text_match,
        "graph_relevance": hints.graph_relevance if hints.graph_relevance is not None else base.graph_relevance,
        "data_quality": hints.data_quality if hints.data_quality is not None else base.data_quality,
        "usage_frequency": hints.usage_frequency if hints.usage_frequency is not None else base.usage_frequency,
        "business_context": hints.business_context if hints.business_context is not None else base.business_context,
    }
