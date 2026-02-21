"""pipeline_logger — @track_class decorator for automatic step-by-step logging."""

from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import json
import logging
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LOG_DIR = _PROJECT_ROOT / "scripts" / "log_process"

_active_log: contextvars.ContextVar[Optional["_LogWriter"]] = contextvars.ContextVar(
    "_active_log", default=None,
)

# Track call depth for indented nested calls
_call_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    "_call_depth", default=0,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PUBLIC API — the decorator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def track_class(
    cls: Optional[Type] = None,
    *,
    log_dir: Optional[str | Path] = None,
    exclude: Optional[Set[str]] = None,
    entry_point: Optional[str] = None,
):
    """Class decorator that wraps every method with detailed step-by-step logging."""
    resolved_dir = Path(log_dir) if log_dir else _DEFAULT_LOG_DIR
    skip = exclude or set()

    def decorator(klass: Type) -> Type:
        original_init = klass.__init__

        @functools.wraps(original_init)
        def new_init(self, *args, **kwargs):
            object.__setattr__(self, "_track_log_dir", resolved_dir)
            object.__setattr__(self, "_track_class_name", klass.__name__)
            object.__setattr__(self, "_track_entry_point", entry_point)
            original_init(self, *args, **kwargs)

        klass.__init__ = new_init

        for name, method in list(inspect.getmembers(klass, predicate=inspect.isfunction)):
            if name.startswith("__") or name in skip:
                continue
            raw = klass.__dict__.get(name)
            if isinstance(raw, (staticmethod, classmethod)):
                continue
            wrapped = _wrap_method(name, method, entry_point)
            setattr(klass, name, wrapped)

        return klass

    if cls is not None:
        return decorator(cls)
    return decorator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  INTERNAL — method wrapper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _wrap_method(name: str, method: Callable, entry_point: Optional[str]) -> Callable:
    is_entry = (entry_point is None and not name.startswith("_")) or name == entry_point
    sig = inspect.signature(method)

    if asyncio.iscoroutinefunction(method):
        @functools.wraps(method)
        async def async_wrapper(self, *args, **kwargs):
            writer = _active_log.get()
            created_here = False
            depth = _call_depth.get()

            if writer is None and is_entry:
                query_val = _extract_query(args, kwargs, sig)
                writer = _LogWriter(
                    class_name=self._track_class_name,
                    query=query_val,
                    log_dir=self._track_log_dir,
                )
                _active_log.set(writer)
                created_here = True

            if writer is None:
                return await method(self, *args, **kwargs)

            args_summary = _summarize_args(args, kwargs, sig)
            step_num = writer.next_step()
            writer.enter(self._track_class_name, name, args_summary, depth, step_num)

            _call_depth.set(depth + 1)
            t0 = time.time()
            try:
                result = await method(self, *args, **kwargs)
                dt = time.time() - t0
                result_detail = _detailed_result(result, name)
                writer.exit(self._track_class_name, name, dt, result_detail, depth, step_num)
                return result
            except Exception as exc:
                writer.error(self._track_class_name, name, time.time() - t0, exc, depth)
                raise
            finally:
                _call_depth.set(depth)
                if created_here:
                    writer.close()
                    _active_log.set(None)

        return async_wrapper
    else:
        @functools.wraps(method)
        def sync_wrapper(self, *args, **kwargs):
            writer = _active_log.get()
            created_here = False
            depth = _call_depth.get()

            if writer is None and is_entry:
                query_val = _extract_query(args, kwargs, sig)
                writer = _LogWriter(
                    class_name=self._track_class_name,
                    query=query_val,
                    log_dir=self._track_log_dir,
                )
                _active_log.set(writer)
                created_here = True

            if writer is None:
                return method(self, *args, **kwargs)

            args_summary = _summarize_args(args, kwargs, sig)
            step_num = writer.next_step()
            writer.enter(self._track_class_name, name, args_summary, depth, step_num)

            _call_depth.set(depth + 1)
            t0 = time.time()
            try:
                result = method(self, *args, **kwargs)
                dt = time.time() - t0
                result_detail = _detailed_result(result, name)
                writer.exit(self._track_class_name, name, dt, result_detail, depth, step_num)
                return result
            except Exception as exc:
                writer.error(self._track_class_name, name, time.time() - t0, exc, depth)
                raise
            finally:
                _call_depth.set(depth)
                if created_here:
                    writer.close()
                    _active_log.set(None)

        return sync_wrapper


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOG WRITER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class _LogWriter:
    """Accumulates detailed log lines and flushes to file on close."""

    __slots__ = ("_lines", "_t0", "_filepath", "_closed", "_step_counter")

    def __init__(self, class_name: str, query: str, log_dir: Path):
        self._t0 = time.time()
        self._closed = False
        self._step_counter = 0
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        slug = _slugify(query)[:50]
        self._filepath = log_dir / f"{ts}_{class_name}_{slug}.log"
        self._lines: List[str] = [
            "=" * 90,
            f"  PIPELINE LOG — {class_name}",
            f"  Query   : {query}",
            f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}",
            "=" * 90,
            "",
        ]

    def next_step(self) -> int:
        self._step_counter += 1
        return self._step_counter

    def _ts(self) -> str:
        return f"+{(time.time() - self._t0) * 1000:8.1f}ms"

    def _indent(self, depth: int) -> str:
        return "│   " * depth

    def enter(self, cls: str, method: str, args_summary: Dict[str, Any],
              depth: int, step: int) -> None:
        ind = self._indent(depth)
        self._lines.append(
            f"[{self._ts()}] {ind}┌─ STEP {step}: {cls}.{method}()"
        )
        if args_summary:
            for k, v in args_summary.items():
                self._lines.append(f"           {ind}│  ▸ {k} = {v}")

    def exit(self, cls: str, method: str, dt: float, result_detail: List[str],
             depth: int, step: int) -> None:
        ind = self._indent(depth)
        dt_ms = dt * 1000
        if result_detail:
            for line in result_detail:
                self._lines.append(f"           {ind}│  {line}")
        self._lines.append(
            f"[{self._ts()}] {ind}└─ DONE  {cls}.{method}() ⏱ {dt_ms:.1f}ms"
        )
        self._lines.append("")

    def error(self, cls: str, method: str, dt: float, exc: Exception,
              depth: int) -> None:
        ind = self._indent(depth)
        self._lines.append(
            f"[{self._ts()}] {ind}└─ ✖ ERROR {cls}.{method}() ⏱ {dt * 1000:.1f}ms"
        )
        self._lines.append(f"           {ind}   {type(exc).__name__}: {exc}")
        for line in traceback.format_exception(type(exc), exc, exc.__traceback__):
            for sub in line.rstrip().split("\n"):
                self._lines.append(f"           {ind}   ! {sub}")
        self._lines.append("")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        total_ms = round((time.time() - self._t0) * 1000)
        self._lines.append("")
        self._lines.append("=" * 90)
        self._lines.append(f"  FINISHED : {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}")
        self._lines.append(f"  TOTAL    : {total_ms}ms  ({self._step_counter} steps)")
        self._lines.append("=" * 90)
        try:
            self._filepath.parent.mkdir(parents=True, exist_ok=True)
            self._filepath.write_text("\n".join(self._lines) + "\n", encoding="utf-8")
            logger.info("📋 Pipeline log → %s", self._filepath)
        except Exception as exc:
            logger.warning("Failed to write pipeline log: %s", exc)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DETAILED RESULT FORMATTERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _detailed_result(result: Any, method_name: str) -> List[str]:
    """Return multiple lines describing the result in detail."""
    lines: List[str] = []

    if result is None:
        lines.append("📭 Result: None")
        return lines

    # ── List of ScoredItem / dicts ──
    if isinstance(result, list):
        lines.append(f"📊 Result: {len(result)} items")
        if not result:
            return lines

        first = result[0]

        # ScoredItem (from reranker or level methods)
        if hasattr(first, "name") and hasattr(first, "label"):
            by_label: Dict[str, list] = {}
            for item in result:
                lbl = getattr(item, "label", "?")
                by_label.setdefault(lbl, []).append(item)
            for lbl, items in by_label.items():
                lines.append(f"   ├─ {lbl}: {len(items)} items")
                for item in items[:10]:
                    name = getattr(item, "name", "?")
                    score = getattr(item, "final_score", None)
                    text_sc = getattr(item, "text_match_score", None)
                    graph_sc = getattr(item, "graph_relevance_score", None)
                    data_q = getattr(item, "data_quality_score", None)
                    biz_ctx = getattr(item, "business_context_score", None)
                    level = getattr(item, "source_level", "")
                    match_type = getattr(item, "match_type", "")
                    hop = getattr(item, "hop_distance", "")
                    parts = []
                    if score is not None:
                        parts.append(f"final={score:.3f}")
                    if text_sc is not None:
                        parts.append(f"text={text_sc:.2f}")
                    if graph_sc is not None:
                        parts.append(f"graph={graph_sc:.2f}")
                    if data_q is not None and data_q > 0:
                        parts.append(f"quality={data_q:.2f}")
                    if biz_ctx is not None and biz_ctx > 0:
                        parts.append(f"biz={biz_ctx:.2f}")
                    score_str = ", ".join(parts)
                    hop_str = f" hop={hop}" if hop else ""
                    lines.append(
                        f"   │  • {name}  [{match_type}/{level}{hop_str}]  ({score_str})"
                    )
            return lines

        # List of dicts
        if isinstance(first, dict):
            for i, item in enumerate(result[:8]):
                preview = {k: _compact(v, 80) for k, v in list(item.items())[:6]}
                lines.append(f"   [{i}] {preview}")
            if len(result) > 8:
                lines.append(f"   ... and {len(result) - 8} more")
            return lines

        # Generic list
        for i, item in enumerate(result[:5]):
            lines.append(f"   [{i}] {_compact(item, 120)}")
        if len(result) > 5:
            lines.append(f"   ... and {len(result) - 5} more")
        return lines

    # ── SchemaSearchResult (to_dict) ──
    if hasattr(result, "to_dict"):
        d = result.to_dict()
        lines.append("📦 Result summary:")
        for k, v in d.items():
            if isinstance(v, list):
                lines.append(f"   ├─ {k}: [{len(v)} items]")
                for item in v[:5]:
                    if isinstance(item, dict):
                        name = item.get("name", "?")
                        score = item.get("score")
                        label = item.get("label", "")
                        summary = item.get("summary", "")[:60]
                        if score is not None:
                            lines.append(f"   │  • {name}  ({label}, score={score:.3f}) {summary}")
                        else:
                            lines.append(f"   │  • {name}  ({label}) {summary}")
                    else:
                        lines.append(f"   │  • {_compact(item, 100)}")
                if len(v) > 5:
                    lines.append(f"   │  ... +{len(v) - 5} more")
            elif isinstance(v, dict):
                lines.append(f"   ├─ {k}:")
                for dk, dv in list(v.items())[:12]:
                    lines.append(f"   │  {dk}: {_compact(dv, 100)}")
            else:
                lines.append(f"   ├─ {k}: {_compact(v, 100)}")
        return lines

    # ── dict ──
    if isinstance(result, dict):
        lines.append(f"📋 Result: dict({len(result)} keys)")
        for k, v in list(result.items())[:10]:
            if isinstance(v, list):
                lines.append(f"   ├─ {k}: [{len(v)} items]")
            elif isinstance(v, dict):
                lines.append(f"   ├─ {k}: dict({len(v)} keys)")
            else:
                lines.append(f"   ├─ {k}: {_compact(v, 100)}")
        return lines

    # ── str ──
    if isinstance(result, str):
        lines.append(f"📝 Result: str(len={len(result)})")
        if len(result) <= 500:
            lines.append(f"   {result}")
        else:
            lines.append(f"   {result[:500]}…")
        return lines

    # ── scalar / other ──
    lines.append(f"📎 Result: {type(result).__name__} = {_compact(result, 200)}")
    return lines


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "_", text)
    return text.strip("_") or "unknown"


def _extract_query(args: tuple, kwargs: dict, sig: inspect.Signature) -> str:
    if "query" in kwargs:
        return str(kwargs["query"])[:200]
    if args:
        return str(args[0])[:200]
    return "unknown"


def _summarize_args(args: tuple, kwargs: dict, sig: inspect.Signature) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    params = list(sig.parameters.values())
    offset = 1 if params and params[0].name == "self" else 0
    for i, arg in enumerate(args):
        idx = i + offset
        name = params[idx].name if idx < len(params) else f"arg{i}"
        if name == "embedding":
            summary[name] = f"vec[{len(arg)}]" if isinstance(arg, list) else _compact(arg)
        else:
            summary[name] = _compact(arg)
    for k, v in kwargs.items():
        if k == "embedding":
            summary[k] = f"vec[{len(v)}]" if isinstance(v, list) else _compact(v)
        else:
            summary[k] = _compact(v)
    return summary


def _compact(obj: Any, max_len: int = 150) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, str):
        return obj[:max_len] + "…" if len(obj) > max_len else obj
    if isinstance(obj, list):
        if not obj:
            return "[]"
        if len(obj) <= 8:
            return [_compact(x, 60) for x in obj]
        return f"[{_compact(obj[0], 40)}, … ({len(obj)} total)]"
    if isinstance(obj, dict):
        if len(obj) <= 5:
            return {k: _compact(v, 60) for k, v in obj.items()}
        keys = list(obj.keys())[:5]
        return f"dict({len(obj)} keys: {keys}…)"
    if hasattr(obj, "name"):
        return f"{type(obj).__name__}(name={getattr(obj, 'name')})"
    s = str(obj)
    return s[:max_len] + "…" if len(s) > max_len else s
