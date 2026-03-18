from __future__ import annotations

import logging
import threading
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

OPENAI_PRICING_PER_1M: dict[str, dict[str, float]] = {
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "text-embedding-3-large": {"input": 0.13, "output": 0.0},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


# ── snapshot model ────────────────────────────────────────────────────────────

class LLMUsageSnapshot(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    embedding_tokens: int = 0
    llm_calls: int = 0
    embedding_calls: int = 0
    cost_usd: float = 0.0
    breakdown: dict[str, Any] = Field(default_factory=dict)


# ── tracker ───────────────────────────────────────────────────────────────────

class LLMCostTracker:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._input_tokens = 0
        self._output_tokens = 0
        self._embedding_tokens = 0
        self._llm_calls = 0
        self._embedding_calls = 0
        self._model_usage: dict[str, dict[str, int]] = {}

    def record_llm_usage(self, *, model: str, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens
            self._llm_calls += 1
            bucket = self._model_usage.setdefault(model, {"input": 0, "output": 0, "calls": 0})
            bucket["input"] += input_tokens
            bucket["output"] += output_tokens
            bucket["calls"] += 1

    def record_embedding_usage(self, *, model: str, total_tokens: int) -> None:
        with self._lock:
            self._embedding_tokens += total_tokens
            self._embedding_calls += 1
            bucket = self._model_usage.setdefault(model, {"input": 0, "output": 0, "calls": 0})
            bucket["input"] += total_tokens
            bucket["calls"] += 1

    def snapshot(self) -> LLMUsageSnapshot:
        with self._lock:
            cost = _compute_cost(self._model_usage)
            return LLMUsageSnapshot(
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                embedding_tokens=self._embedding_tokens,
                llm_calls=self._llm_calls,
                embedding_calls=self._embedding_calls,
                cost_usd=round(cost, 6),
                breakdown={
                    model: {
                        "input_tokens": data["input"],
                        "output_tokens": data["output"],
                        "calls": data["calls"],
                        "cost_usd": round(_compute_model_cost(model, data), 6),
                    }
                    for model, data in self._model_usage.items()
                },
            )

    def reset(self) -> LLMUsageSnapshot:
        snap = self.snapshot()
        with self._lock:
            self._input_tokens = 0
            self._output_tokens = 0
            self._embedding_tokens = 0
            self._llm_calls = 0
            self._embedding_calls = 0
            self._model_usage.clear()
        return snap


# ── OpenAI client wrappers ────────────────────────────────────────────────────

class _TrackedCompletions:
    """Thin proxy over AsyncCompletions that records token usage."""

    def __init__(self, original: Any, tracker: LLMCostTracker) -> None:
        self._original = original
        self._tracker = tracker

    async def create(self, **kwargs: Any) -> Any:
        response = await self._original.create(**kwargs)
        model = getattr(response, "model", kwargs.get("model", "unknown"))
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._tracker.record_llm_usage(
                model=model,
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            )
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)


class _TrackedEmbeddings:
    """Thin proxy over AsyncEmbeddings that records token usage."""

    def __init__(self, original: Any, tracker: LLMCostTracker) -> None:
        self._original = original
        self._tracker = tracker

    async def create(self, **kwargs: Any) -> Any:
        response = await self._original.create(**kwargs)
        model = kwargs.get("model", "unknown")
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._tracker.record_embedding_usage(
                model=model,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
            )
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)


class _TrackedResponses:
    """Thin proxy over AsyncResponses that records token usage."""

    def __init__(self, original: Any, tracker: LLMCostTracker) -> None:
        self._original = original
        self._tracker = tracker

    async def parse(self, **kwargs: Any) -> Any:
        response = await self._original.parse(**kwargs)
        model = kwargs.get("model", "unknown")
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._tracker.record_llm_usage(
                model=model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
            )
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)


class TrackedAsyncOpenAI:
    """AsyncOpenAI wrapper that intercepts calls and records cost via LLMCostTracker."""

    def __init__(self, client: AsyncOpenAI, tracker: LLMCostTracker) -> None:
        self._client = client
        self._tracker = tracker
        self.chat = type("_Chat", (), {
            "completions": _TrackedCompletions(client.chat.completions, tracker),
        })()
        self.embeddings = _TrackedEmbeddings(client.embeddings, tracker)
        self.responses = _TrackedResponses(client.responses, tracker)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def wrap_openai_client(client: AsyncOpenAI, *, tracker: LLMCostTracker) -> TrackedAsyncOpenAI:
    return TrackedAsyncOpenAI(client, tracker)


# ── helpers ───────────────────────────────────────────────────────────────────

def _compute_model_cost(model: str, data: dict[str, int]) -> float:
    pricing = OPENAI_PRICING_PER_1M.get(model)
    if pricing is None:
        return 0.0
    return (data["input"] / 1_000_000) * pricing["input"] + (data["output"] / 1_000_000) * pricing["output"]


def _compute_cost(model_usage: dict[str, dict[str, int]]) -> float:
    return sum(_compute_model_cost(model, data) for model, data in model_usage.items())
