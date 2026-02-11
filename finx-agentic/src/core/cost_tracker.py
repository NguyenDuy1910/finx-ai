from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from agno.agent import RunOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing tables (USD per 1 M tokens) – update as prices change
# ---------------------------------------------------------------------------
# fmt: off
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Google Gemini
    "gemini-2.5-flash":     {"input": 0.15,  "output": 0.60},
    "gemini-2.5-pro":       {"input": 1.25,  "output": 10.00},
    "gemini-2.0-flash":     {"input": 0.10,  "output": 0.40},
    "gemini-flash-latest":  {"input": 0.10,  "output": 0.40},
    # OpenAI
    "gpt-4o":               {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":          {"input": 0.15,  "output": 0.60},
    "gpt-4-turbo":          {"input": 10.00, "output": 30.00},
    "gpt-4":                {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo":        {"input": 0.50,  "output": 1.50},
    "o1":                   {"input": 15.00, "output": 60.00},
    "o1-mini":              {"input": 3.00,  "output": 12.00},
    "o3-mini":              {"input": 1.10,  "output": 4.40},
    # Anthropic
    "claude-sonnet-4-20250514":  {"input": 3.00,  "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307":   {"input": 0.25,  "output": 1.25},
    "claude-3-opus-20240229":    {"input": 15.00, "output": 75.00},
    # Embedding
    "text-embedding-3-large":  {"input": 0.13, "output": 0.0},
    "text-embedding-3-small":  {"input": 0.02, "output": 0.0},
}
# fmt: on


def estimate_cost(
    model: Optional[str],
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> Optional[float]:
    """Return estimated cost in USD, or *None* if the model is unknown."""
    if not model:
        return None
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        # Try partial match (e.g. "gemini-2.5-flash-preview" → "gemini-2.5-flash")
        for key, val in MODEL_PRICING.items():
            if key in model or model in key:
                pricing = val
                break
    if pricing is None:
        return None
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


@dataclass
class StepMetrics:
    step: str
    agent_name: Optional[str] = None
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    duration_s: Optional[float] = None
    time_to_first_token_s: Optional[float] = None
    cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None and v != 0}


@dataclass
class CostTracker:
    """Accumulates metrics across multiple agent steps."""

    steps: List[StepMetrics] = field(default_factory=list)
    _wall_start: float = field(default_factory=time.monotonic)

    # ----- public API -----

    def track(self, response: RunOutput, step: str = "") -> StepMetrics:
        """Extract metrics from a RunOutput and append them."""
        m = response.metrics
        model = response.model

        if m is None:
            sm = StepMetrics(
                step=step,
                agent_name=response.agent_name,
                model=model,
            )
            self.steps.append(sm)
            return sm

        # Use provider-reported cost if available, else estimate
        cost = m.cost
        if cost is None:
            cost = estimate_cost(model, m.input_tokens, m.output_tokens)

        sm = StepMetrics(
            step=step,
            agent_name=response.agent_name,
            model=model,
            input_tokens=m.input_tokens,
            output_tokens=m.output_tokens,
            total_tokens=m.total_tokens,
            reasoning_tokens=m.reasoning_tokens,
            cache_read_tokens=m.cache_read_tokens,
            cache_write_tokens=m.cache_write_tokens,
            duration_s=round(m.duration, 4) if m.duration else None,
            time_to_first_token_s=round(m.time_to_first_token, 4) if m.time_to_first_token else None,
            cost_usd=round(cost, 6) if cost else None,
        )
        self.steps.append(sm)
        return sm

    # ----- aggregation -----

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens for s in self.steps)

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens for s in self.steps)

    @property
    def total_tokens(self) -> int:
        return sum(s.total_tokens for s in self.steps)

    @property
    def total_cost_usd(self) -> float:
        return sum(s.cost_usd for s in self.steps if s.cost_usd is not None)

    @property
    def total_duration_s(self) -> float:
        return sum(s.duration_s for s in self.steps if s.duration_s is not None)

    @property
    def wall_time_s(self) -> float:
        return round(time.monotonic() - self._wall_start, 3)

    # ----- output -----

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "totals": {
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "total_tokens": self.total_tokens,
                "cost_usd": round(self.total_cost_usd, 6),
                "llm_duration_s": round(self.total_duration_s, 3),
                "wall_time_s": self.wall_time_s,
                "num_steps": len(self.steps),
            },
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def print_summary(self) -> None:
        """Print a human-readable cost summary table."""
        print("\n" + "=" * 80)
        print("📊  AGENT RUN COST SUMMARY")
        print("=" * 80)
        print(
            f"{'Step':<25} {'Model':<22} {'In Tok':>8} {'Out Tok':>8} "
            f"{'Duration':>9} {'Cost ($)':>10}"
        )
        print("-" * 80)
        for s in self.steps:
            model_short = (s.model or "?")[:21]
            dur = f"{s.duration_s:.2f}s" if s.duration_s else "-"
            cost = f"${s.cost_usd:.6f}" if s.cost_usd is not None else "-"
            print(
                f"{s.step:<25} {model_short:<22} {s.input_tokens:>8,} {s.output_tokens:>8,} "
                f"{dur:>9} {cost:>10}"
            )
        print("-" * 80)
        dur_total = f"{self.total_duration_s:.2f}s"
        print(
            f"{'TOTAL':<25} {'':<22} {self.total_input_tokens:>8,} {self.total_output_tokens:>8,} "
            f"{dur_total:>9} {'$' + f'{self.total_cost_usd:.6f}':>10}"
        )
        print(f"{'Wall time':<25} {self.wall_time_s:.2f}s")
        print("=" * 80 + "\n")
