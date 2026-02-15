"""QueryAnalyzer — extracts intent, entities, complexity and temporal context from a query."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class QueryIntent(str, Enum):
    SELECT = "select"
    JOIN = "join"
    AGGREGATE = "aggregate"
    FILTER = "filter"
    COUNT = "count"
    TREND = "trend"
    COMPARISON = "comparison"
    LOOKUP = "lookup"
    SCHEMA_EXPLORATION = "schema_exploration"
    UNKNOWN = "unknown"


class QueryComplexity(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class QueryAnalysis:
    original_query: str
    entities: List[str] = field(default_factory=list)
    intent: QueryIntent = QueryIntent.UNKNOWN
    complexity: QueryComplexity = QueryComplexity.SIMPLE
    temporal_context: Optional[str] = None
    aggregation_functions: List[str] = field(default_factory=list)
    filter_terms: List[str] = field(default_factory=list)
    key_business_terms: List[str] = field(default_factory=list)
    database_hint: Optional[str] = None
    is_vietnamese: bool = False


# ── keyword banks ────────────────────────────────────────────────────

_AGGREGATE_KW = {
    "sum", "total", "count", "average", "avg", "min", "max", "mean",
    "tổng", "đếm", "trung bình", "lớn nhất", "nhỏ nhất",
    "group by", "nhóm theo",
}

_JOIN_KW = {
    "join", "kết hợp", "liên kết", "relate", "relationship",
    "between", "giữa", "across", "connect",
}

_TREND_KW = {
    "trend", "xu hướng", "over time", "theo thời gian",
    "monthly", "daily", "weekly", "yearly",
    "hàng tháng", "hàng ngày", "hàng tuần", "hàng năm",
    "growth", "tăng trưởng", "change", "thay đổi",
}

_COMPARISON_KW = {
    "compare", "so sánh", "versus", "vs", "difference", "chênh lệch",
    "higher", "lower", "more", "less", "top", "bottom",
    "cao hơn", "thấp hơn", "nhiều hơn", "ít hơn",
}

_SCHEMA_KW = {
    "table", "column", "schema", "bảng", "cột", "field",
    "structure", "cấu trúc", "what tables", "show me",
    "describe", "mô tả", "list",
}

_FILTER_KW = {
    "where", "filter", "lọc", "condition", "điều kiện",
    "greater", "less", "equal", "between", "in", "not",
    "status", "trạng thái", "type", "loại",
}

_COUNT_KW = {
    "how many", "bao nhiêu", "count", "đếm", "number of", "số lượng",
}

_TEMPORAL_PATTERNS = [
    (r"(?:last|previous)\s+(?:quarter|month|week|year|day)", "temporal_relative"),
    (r"(?:this|current)\s+(?:quarter|month|week|year|day)", "temporal_current"),
    (r"(?:today|yesterday|tomorrow)", "temporal_day"),
    (r"\b(?:Q[1-4])\b", "temporal_quarter"),
    (r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", "temporal_date"),
    (r"\b\d{4}[-/]\d{2}\b", "temporal_month"),
    (r"\b\d{4}\b", "temporal_year"),
    (r"(?:tháng|quý|tuần|năm|ngày)\s+(?:trước|này|nay|vừa qua)", "temporal_relative_vi"),
    (r"hôm (?:nay|qua)", "temporal_day_vi"),
]

_VIETNAMESE_TERMS = {
    "khách hàng": "customer",
    "tài khoản": "account",
    "giao dịch": "transaction",
    "chuyển khoản": "transfer",
    "thanh toán": "payment",
    "số dư": "balance",
    "tiền gửi": "deposit",
    "khoản vay": "loan",
    "lãi suất": "interest_rate",
    "thẻ": "card",
    "chi nhánh": "branch",
    "sản phẩm": "product",
    "hóa đơn": "bill",
    "ekyc": "ekyc",
    "onboarding": "onboarding",
    "xác thực": "authentication",
    "chiến dịch": "campaign",
    "nợ": "debt",
    "phân loại nợ": "debt_classification",
}

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "of", "for", "to", "in", "on", "at", "by", "with", "from",
    "and", "or", "but", "not", "no", "all", "each", "every",
    "show", "me", "give", "get", "find", "list", "display",
    "what", "which", "how", "who", "where", "when",
    "please", "can", "could", "would", "should",
    "i", "want", "need", "like",
    "là", "của", "cho", "với", "trong", "từ", "và", "hoặc",
    "được", "có", "không", "tôi", "hãy", "xin",
}


class QueryAnalyzer:
    """Stateless query analyzer — no async, no LLM, pure heuristics."""

    def analyze(self, query: str) -> QueryAnalysis:
        q_lower = query.lower().strip()
        is_vn = self._detect_vietnamese(q_lower)

        return QueryAnalysis(
            original_query=query,
            entities=self._extract_entities(q_lower, is_vn),
            intent=self._classify_intent(q_lower),
            complexity=self._classify_complexity(
                q_lower, self._extract_entities(q_lower, is_vn), self._classify_intent(q_lower),
            ),
            temporal_context=self._extract_temporal(q_lower),
            aggregation_functions=self._extract_aggregations(q_lower),
            filter_terms=self._extract_filters(q_lower),
            key_business_terms=self._extract_business_terms(q_lower, is_vn),
            database_hint=self._extract_database_hint(q_lower),
            is_vietnamese=is_vn,
        )

    @staticmethod
    def _detect_vietnamese(text: str) -> bool:
        vn_chars = set("àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ")
        return any(c in vn_chars for c in text)

    @staticmethod
    def _extract_entities(text: str, is_vn: bool) -> List[str]:
        entities: list[str] = []
        if is_vn:
            for vn_term, en_entity in _VIETNAMESE_TERMS.items():
                if vn_term in text:
                    entities.append(en_entity)
        tokens = re.findall(
            r"[a-zA-Zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ_]+",
            text,
        )
        meaningful = [t for t in tokens if t not in _STOPWORDS and len(t) > 2]
        for token in meaningful:
            if token not in entities:
                entities.append(token)
        return list(dict.fromkeys(entities))

    @staticmethod
    def _classify_intent(text: str) -> QueryIntent:
        if any(kw in text for kw in _SCHEMA_KW):
            return QueryIntent.SCHEMA_EXPLORATION
        if any(kw in text for kw in _COUNT_KW):
            return QueryIntent.COUNT
        if any(kw in text for kw in _TREND_KW):
            return QueryIntent.TREND
        if any(kw in text for kw in _COMPARISON_KW):
            return QueryIntent.COMPARISON
        if any(kw in text for kw in _AGGREGATE_KW):
            return QueryIntent.AGGREGATE
        if any(kw in text for kw in _JOIN_KW):
            return QueryIntent.JOIN
        if any(kw in text for kw in _FILTER_KW):
            return QueryIntent.FILTER
        return QueryIntent.SELECT

    @staticmethod
    def _classify_complexity(
        text: str, entities: List[str], intent: QueryIntent,
    ) -> QueryComplexity:
        entity_count = len(entities)
        has_join = any(kw in text for kw in _JOIN_KW)
        has_agg = any(kw in text for kw in _AGGREGATE_KW)
        has_trend = any(kw in text for kw in _TREND_KW)
        if entity_count >= 4 or (has_join and has_agg) or has_trend:
            return QueryComplexity.COMPLEX
        if entity_count >= 2 or has_join or has_agg or intent in (
            QueryIntent.JOIN, QueryIntent.AGGREGATE, QueryIntent.TREND,
        ):
            return QueryComplexity.MEDIUM
        return QueryComplexity.SIMPLE

    @staticmethod
    def _extract_temporal(text: str) -> Optional[str]:
        for pattern, _label in _TEMPORAL_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return m.group(0)
        return None

    @staticmethod
    def _extract_aggregations(text: str) -> List[str]:
        return [kw for kw in _AGGREGATE_KW if kw in text]

    @staticmethod
    def _extract_filters(text: str) -> List[str]:
        return [kw for kw in _FILTER_KW if kw in text]

    @staticmethod
    def _extract_business_terms(text: str, is_vn: bool) -> List[str]:
        terms: List[str] = []
        if is_vn:
            for vn_term in _VIETNAMESE_TERMS:
                if vn_term in text:
                    terms.append(vn_term)
        for m in re.finditer(r'"([^"]+)"', text):
            terms.append(m.group(1))
        for m in re.finditer(r"'([^']+)'", text):
            terms.append(m.group(1))
        return terms

    @staticmethod
    def _extract_database_hint(text: str) -> Optional[str]:
        m = re.search(r"(?:database|db)[:\s]+([a-z_]+)", text)
        if m:
            return m.group(1)
        for db in ("gold_zone", "silver_zone", "bronze_zone", "raw_zone", "staging"):
            if db in text:
                return db
        return None
