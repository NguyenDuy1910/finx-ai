"""Class decorator – automatic **deep** runtime tracing for every method.

Usage
-----
::

    from src.core.log_tracker import log_tracker

    @log_tracker                          # defaults (deep_trace=True)
    class MyService:
        ...

    @log_tracker(level="DEBUG", deep_trace=False)   # lightweight mode
    class MyService:
        ...

Deep-trace mode (default) instruments every method **without touching
its source code** and produces a *human-friendly* log:

┌─ CALL   method(args)
│  ── Initializing local variables ──
│  SET  var_a = 'hello'
│  SET  var_b = 42
│  ── Executing logic ──
│  STEP   88 │ result = await self.some_call(...)
│  AWAIT  #1 │ self.some_call  → <result>  [12.3 ms]
│  ── Building response ──
│  SET  documents = [...]
└─ RETURN method → [...]  [150.2 ms]

Key improvements over raw tracing:
  • Only **newly-assigned** variables are logged (diff-based, no spam)
  • Multi-line statements are **collapsed** into one logical step
  • Async methods use ``sys.settrace`` callback (no manual coroutine
    driving) – compatible with ``asyncio.Future``
  • Long values are truncated; ``input`` / ``query`` args get a
    dedicated short summary

All output → ``scripts/log_process/<ClassName>_<YYYYMMDD>.log``.

The decorator **never** changes return values or swallows exceptions.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import linecache
import logging
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import (
    Any,
    Callable,
    FrozenSet,
    Optional,
    Set,
    Type,
    TypeVar,
    Union,
    overload,
)

T = TypeVar("T")

# ── Defaults ────────────────────────────────────────────────────────────

_DEFAULT_LEVEL = "DEBUG"
_DEFAULT_MAX_STR_LEN = 120
_DEFAULT_LOG_RESULT = True
_DEFAULT_LOG_ARGS = True
_DEFAULT_INDENT = True
_DEFAULT_DEEP_TRACE = True
_DEFAULT_LOG_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir,
    "scripts", "log_process",
)
_DUNDER_WHITELIST: FrozenSet[str] = frozenset({"__call__", "__getitem__", "__setitem__"})

# Variables whose *full repr* is never interesting on every line
_NOISY_VAR_NAMES: FrozenSet[str] = frozenset({
    "self", "cls", "args", "kwargs", "input", "query", "request",
})

_file_handlers_attached: set[str] = set()


# ── File handler setup ──────────────────────────────────────────────────

def _setup_file_handler(
    logger: logging.Logger,
    log_dir: str,
    cls_name: str,
    log_level: int,
) -> None:
    if logger.name in _file_handlers_attached:
        return
    log_path = Path(log_dir).resolve()
    log_path.mkdir(parents=True, exist_ok=True)
    safe_name = cls_name.replace(".", "_").replace("<", "").replace(">", "")
    date_str = datetime.now().strftime("%Y%m%d")
    file_name = log_path / f"{safe_name}_{date_str}.log"
    handler = RotatingFileHandler(
        filename=str(file_name), maxBytes=10 * 1024 * 1024,
        backupCount=5, encoding="utf-8",
    )
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    if logger.level == logging.NOTSET or logger.level > log_level:
        logger.setLevel(log_level)
    _file_handlers_attached.add(logger.name)


# ── Depth tracking ──────────────────────────────────────────────────────

_call_depth_var: dict[int, int] = {}


def _get_depth_key() -> int:
    try:
        task = asyncio.current_task()
        if task is not None:
            return id(task)
    except RuntimeError:
        pass
    import threading
    return threading.current_thread().ident or 0


@contextmanager
def _track_depth():
    key = _get_depth_key()
    _call_depth_var[key] = _call_depth_var.get(key, 0) + 1
    try:
        yield _call_depth_var[key]
    finally:
        _call_depth_var[key] -= 1
        if _call_depth_var[key] <= 0:
            _call_depth_var.pop(key, None)


# ── Formatting helpers ──────────────────────────────────────────────────

def _truncate(value: Any, max_len: int) -> str:
    try:
        text = repr(value)
    except Exception:
        text = f"<repr-error: {type(value).__name__}>"
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _smart_summary(name: str, value: Any, max_len: int) -> str:
    """Produce a *compact* human-readable summary for a variable.

    For known-noisy variables (input/query with big JSON), extract just
    the domain/intent rather than dumping the whole blob.
    Only applies when the value actually exceeds ``max_len``.
    """
    if name in _NOISY_VAR_NAMES:
        s = str(value)
        # Only compact-summarise when the value is truly too long
        if len(s) > max_len:
            intent_m = re.search(r'"intent"\s*:\s*"([^"]+)"', s)
            domain_m = re.search(r'"domain"\s*:\s*"([^"]+)"', s)
            if intent_m or domain_m:
                parts = []
                if intent_m:
                    parts.append(f"intent={intent_m.group(1)}")
                if domain_m:
                    parts.append(f"domain={domain_m.group(1)}")
                return f"<{', '.join(parts)}, len={len(s)}>"
            return f"<{type(value).__name__}, len={len(s)}>"
    return _truncate(value, max_len)


def _format_args(args: tuple, kwargs: dict, max_len: int, skip_self: bool = True) -> str:
    parts: list[str] = []
    iterable_args = args[1:] if skip_self and args else args
    for i, a in enumerate(iterable_args):
        parts.append(_smart_summary(f"arg{i}", a, max_len))
    for k, v in kwargs.items():
        parts.append(f"{k}={_smart_summary(k, v, max_len)}")
    return ", ".join(parts)


def _make_call_id() -> str:
    return uuid.uuid4().hex[:8]


def _diff_locals(prev: dict[str, Any], curr_frame, max_str_len: int = _DEFAULT_MAX_STR_LEN) -> dict[str, str]:
    """Return only variables that are NEW or CHANGED since last snapshot.

    Skips self/cls and dunder names. Values are already formatted strings.
    """
    changed: dict[str, str] = {}
    for k, v in curr_frame.f_locals.items():
        if k.startswith("__") or k in ("self", "cls"):
            continue
        prev_id = prev.get(k, _SENTINEL)
        if prev_id is _SENTINEL:
            # New variable
            changed[k] = _smart_summary(k, v, max_str_len)
            prev[k] = id(v)
        elif id(v) != prev_id:
            # Changed value
            changed[k] = _smart_summary(k, v, max_str_len)
            prev[k] = id(v)
    return changed


_SENTINEL = object()


def _is_continuation_line(src: str) -> bool:
    """Return True if ``src`` looks like a continuation of a multi-line call.

    Lines that are just keyword arguments (``key=value,``), closing
    parens, or blank are continuation lines.
    """
    stripped = src.strip()
    if not stripped:
        return True
    # Closing paren / bracket
    if stripped in (")", "],", ");", "),", "]", "}", "},"):
        return True
    # keyword=value, (part of a function call spread across lines)
    if re.match(r"^[a-zA-Z_]\w*\s*=\s*.+,?\s*$", stripped) and "==" not in stripped:
        # But not if it's a standalone assignment like `x = some_func()`
        # Check: if the line has balanced parens and doesn't end with `,`
        # it's probably a standalone assignment, not a call arg
        if stripped.endswith(","):
            return True
        # Count open/close parens — if unbalanced, it's a continuation
        if stripped.count("(") != stripped.count(")"):
            return True
    return False


_STRUCTURAL_KEYWORDS: FrozenSet[str] = frozenset({
    "try:", "except", "finally:", "else:", "elif",
    "if", "for", "while", "with", "return", "yield",
})


def _is_structural_line(src: str) -> bool:
    """Return True if the line is a structural keyword (try/except/if/for/etc)."""
    stripped = src.strip()
    for kw in _STRUCTURAL_KEYWORDS:
        if stripped.startswith(kw):
            return True
    return False


# ── Deep tracer (sys.settrace) ──────────────────────────────────────────

class _DeepTracer:
    """Human-friendly trace callback for a single method invocation.

    Instead of dumping ALL variables on every line, this tracer:
      • Only logs **newly assigned / changed** variables (diff-based).
      • **Collapses** multi-line statements (e.g. multi-line function calls)
        into a single STEP log.
      • Groups variable assignments into a compact SET block.
      • Shows sub-calls with a clean SUBCALL / SUBRETURN pair.
    """

    def __init__(self, target_code, logger, level, max_str_len, prefix):
        self._target_code = target_code
        self._logger = logger
        self._level = level
        self._max = max_str_len
        self._prefix = prefix
        self._sub_depth = 0
        # Track variable identity for diff-based logging
        self._prev_locals: dict[str, Any] = {}
        # Track the first line of the current logical statement
        self._stmt_start_line: int | None = None
        self._stmt_src: str = ""

    # -- installed as the global trace function -------------------------

    def __call__(self, frame, event, arg):
        if frame.f_code is self._target_code:
            return self._trace_target
        return None

    # -- local trace for the target frame -------------------------------

    def _trace_target(self, frame, event, arg):
        if event == "line":
            lineno = frame.f_lineno
            src = linecache.getline(frame.f_code.co_filename, lineno).rstrip()
            stripped = src.strip()

            # ── Collapse continuation lines ──
            if self._stmt_start_line is not None and _is_continuation_line(stripped):
                # Still part of the previous multi-line statement, skip
                return self._trace_target

            # ── Flush previous statement if we hit a new one ──
            if self._stmt_start_line is not None:
                self._flush_step(frame)

            # Record start of new statement
            self._stmt_start_line = lineno
            self._stmt_src = stripped

            return self._trace_target

        elif event == "call":
            # Flush the pending statement before sub-call
            if self._stmt_start_line is not None:
                self._flush_step_no_vars()

            self._sub_depth += 1
            name = frame.f_code.co_name
            src_file = os.path.basename(frame.f_code.co_filename)
            indent = "│  " * self._sub_depth
            self._logger.log(
                self._level,
                "%s│  %s┌─ SUBCALL  %s (%s)",
                self._prefix, indent, name, src_file,
            )
            return self._trace_subcall

        elif event == "return":
            # Flush any remaining statement
            if self._stmt_start_line is not None:
                self._flush_step(frame)

        elif event == "exception":
            exc_type, exc_value, _ = arg
            # StopIteration is normal for async coroutines — not a real error
            if exc_type is StopIteration or exc_type is GeneratorExit:
                return self._trace_target
            self._logger.log(
                logging.ERROR,
                "%s│  ✖ EXCEPTION line %d │ %s: %s",
                self._prefix, frame.f_lineno,
                exc_type.__name__ if exc_type else "?",
                str(exc_value)[:self._max] if exc_value else "",
            )

        return self._trace_target

    def _flush_step(self, frame):
        """Log the current statement + any variable changes."""
        lineno = self._stmt_start_line
        src = self._stmt_src
        self._stmt_start_line = None
        self._stmt_src = ""

        # Skip empty / whitespace-only source lines
        if not src.strip():
            # Still compute diff so prev_locals stays up to date
            _diff_locals(self._prev_locals, frame, self._max)
            return

        # Check what changed
        changed = _diff_locals(self._prev_locals, frame, self._max)

        # Log the source line
        self._logger.log(
            self._level,
            "%s│  STEP %3d │ %s",
            self._prefix, lineno, src,
        )

        # Log only the NEW/CHANGED variables compactly
        if changed:
            parts = [f"{k}={v}" for k, v in changed.items()]
            # Group into lines of ~120 chars
            line = ""
            for p in parts:
                if line and len(line) + len(p) > 110:
                    self._logger.log(
                        self._level,
                        "%s│         SET  %s",
                        self._prefix, line,
                    )
                    line = p
                else:
                    line = f"{line}, {p}" if line else p
            if line:
                self._logger.log(
                    self._level,
                    "%s│         SET  %s",
                    self._prefix, line,
                )

    def _flush_step_no_vars(self):
        """Log the pending statement without checking vars (before subcall)."""
        if self._stmt_start_line is None:
            return
        if not self._stmt_src.strip():
            self._stmt_start_line = None
            self._stmt_src = ""
            return
        self._logger.log(
            self._level,
            "%s│  STEP %3d │ %s",
            self._prefix, self._stmt_start_line, self._stmt_src,
        )
        self._stmt_start_line = None
        self._stmt_src = ""

    # -- local trace for one-level-deep sub-calls -----------------------

    def _trace_subcall(self, frame, event, arg):
        indent = "│  " * self._sub_depth
        if event == "return":
            self._logger.log(
                self._level,
                "%s│  %s└─ SUBRETURN %s → %s",
                self._prefix, indent, frame.f_code.co_name,
                _truncate(arg, self._max),
            )
            self._sub_depth = max(0, self._sub_depth - 1)
            return None
        if event == "exception":
            exc_type, exc_value, _ = arg
            # StopIteration is normal for async coroutines
            if exc_type is StopIteration or exc_type is GeneratorExit:
                self._sub_depth = max(0, self._sub_depth - 1)
                return None
            self._logger.log(
                logging.ERROR,
                "%s│  %s└─ SUBERROR %s ✖ %s: %s",
                self._prefix, indent, frame.f_code.co_name,
                exc_type.__name__ if exc_type else "?",
                str(exc_value)[:self._max] if exc_value else "",
            )
            self._sub_depth = max(0, self._sub_depth - 1)
            return None
        return None


# ── Sync wrapper ────────────────────────────────────────────────────────

def _wrap_sync(fn, cls_name, logger, level, max_str_len, log_args, log_result, use_indent, deep_trace):
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        call_id = _make_call_id()
        qualified = f"{cls_name}.{fn.__name__}"

        with _track_depth() as depth:
            indent = "│  " * (depth - 1) if use_indent else ""
            prefix = f"[{call_id}] {indent}"

            if log_args:
                logger.log(level, "%s┌─ CALL  %s(%s)", prefix, qualified,
                           _format_args(args, kwargs, max_str_len))
            else:
                logger.log(level, "%s┌─ CALL  %s(…)", prefix, qualified)

            tracer_obj = None
            old_trace = None
            if deep_trace:
                tracer_obj = _DeepTracer(fn.__code__, logger, level, max_str_len, prefix)
                old_trace = sys.gettrace()
                sys.settrace(tracer_obj)

            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                elapsed = (time.perf_counter() - t0) * 1000
                if log_result:
                    logger.log(level, "%s└─ RETURN %s → %s  [%.1f ms]",
                               prefix, qualified, _truncate(result, max_str_len), elapsed)
                else:
                    logger.log(level, "%s└─ RETURN %s  [%.1f ms]", prefix, qualified, elapsed)
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - t0) * 1000
                logger.log(logging.ERROR, "%s└─ ERROR  %s ✖ %s: %s  [%.1f ms]",
                           prefix, qualified, type(exc).__name__,
                           str(exc)[:max_str_len], elapsed)
                raise
            finally:
                if deep_trace:
                    sys.settrace(old_trace)

    return wrapper


# ── Async wrapper ───────────────────────────────────────────────────────

def _wrap_async(fn, cls_name, logger, level, max_str_len, log_args, log_result, use_indent, deep_trace):
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        call_id = _make_call_id()
        qualified = f"{cls_name}.{fn.__name__}"

        with _track_depth() as depth:
            indent_str = "│  " * (depth - 1) if use_indent else ""
            prefix = f"[{call_id}] {indent_str}"

            if log_args:
                logger.log(level, "%s┌─ CALL  %s(%s)", prefix, qualified,
                           _format_args(args, kwargs, max_str_len))
            else:
                logger.log(level, "%s┌─ CALL  %s(…)", prefix, qualified)

            # For async: install sys.settrace as a callback so it captures
            # synchronous segments. Unlike _drive_coroutine_traced, this
            # does NOT manually drive the coroutine — so asyncio.Future
            # and task scheduling work normally.
            tracer_obj = None
            old_trace = None
            if deep_trace:
                tracer_obj = _DeepTracer(fn.__code__, logger, level, max_str_len, prefix)
                old_trace = sys.gettrace()
                sys.settrace(tracer_obj)

            t0 = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)

                elapsed = (time.perf_counter() - t0) * 1000
                if log_result:
                    logger.log(level, "%s└─ RETURN %s → %s  [%.1f ms]",
                               prefix, qualified, _truncate(result, max_str_len), elapsed)
                else:
                    logger.log(level, "%s└─ RETURN %s  [%.1f ms]", prefix, qualified, elapsed)
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - t0) * 1000
                logger.log(logging.ERROR, "%s└─ ERROR  %s ✖ %s: %s  [%.1f ms]",
                           prefix, qualified, type(exc).__name__,
                           str(exc)[:max_str_len], elapsed)
                raise
            finally:
                if deep_trace:
                    sys.settrace(old_trace)

    return wrapper


# ── Class decorator logic ───────────────────────────────────────────────

def _should_wrap(name: str, obj: Any, ignore: Set[str]) -> bool:
    if name in ignore:
        return False
    if not callable(obj) and not isinstance(obj, (staticmethod, classmethod)):
        return False
    if name.startswith("__") and name.endswith("__") and name not in _DUNDER_WHITELIST:
        return False
    if isinstance(obj, property):
        return False
    return True


def _apply_tracker(cls, level, max_str_len, log_result, log_args,
                   ignore_methods, indent, logger_name, log_dir, deep_trace):
    log_level = getattr(logging, level.upper(), logging.DEBUG)
    _logger = logging.getLogger(logger_name or f"tracker.{cls.__module__}.{cls.__qualname__}")
    cls_name = cls.__qualname__
    resolved_dir = log_dir or _DEFAULT_LOG_DIR
    _setup_file_handler(_logger, resolved_dir, cls_name, log_level)

    for name, obj in list(vars(cls).items()):
        if not _should_wrap(name, obj, ignore_methods):
            continue
        raw = obj
        is_static = isinstance(obj, staticmethod)
        is_classmethod = isinstance(obj, classmethod)
        if is_static:
            raw = obj.__func__
        elif is_classmethod:
            raw = obj.__func__
        if not callable(raw):
            continue

        if asyncio.iscoroutinefunction(raw):
            wrapped = _wrap_async(raw, cls_name, _logger, log_level,
                                  max_str_len, log_args, log_result, indent, deep_trace)
        elif inspect.isgeneratorfunction(raw) or inspect.isasyncgenfunction(raw):
            continue
        else:
            wrapped = _wrap_sync(raw, cls_name, _logger, log_level,
                                 max_str_len, log_args, log_result, indent, deep_trace)

        if is_static:
            wrapped = staticmethod(wrapped)
        elif is_classmethod:
            wrapped = classmethod(wrapped)
        setattr(cls, name, wrapped)

    return cls


# ── Public API ──────────────────────────────────────────────────────────

@overload
def log_tracker(cls: Type[T]) -> Type[T]: ...

@overload
def log_tracker(
    *,
    level: str = ...,
    max_str_len: int = ...,
    log_result: bool = ...,
    log_args: bool = ...,
    ignore_methods: Optional[Set[str]] = ...,
    indent: bool = ...,
    logger_name: Optional[str] = ...,
    log_dir: Optional[str] = ...,
    deep_trace: bool = ...,
) -> Callable[[Type[T]], Type[T]]: ...

def log_tracker(
    cls: Optional[Type[T]] = None,
    *,
    level: str = _DEFAULT_LEVEL,
    max_str_len: int = _DEFAULT_MAX_STR_LEN,
    log_result: bool = _DEFAULT_LOG_RESULT,
    log_args: bool = _DEFAULT_LOG_ARGS,
    ignore_methods: Optional[Set[str]] = None,
    indent: bool = _DEFAULT_INDENT,
    logger_name: Optional[str] = None,
    log_dir: Optional[str] = None,
    deep_trace: bool = _DEFAULT_DEEP_TRACE,
) -> Union[Type[T], Callable[[Type[T]], Type[T]]]:
    """Class decorator — instruments every method with call tracing.

    Parameters
    ----------
    level : str
        Log level name.
    max_str_len : int
        Max repr length for args/results.
    log_result / log_args : bool
        Whether to log return values / input arguments.
    ignore_methods : set[str] | None
        Method names to skip.
    indent : bool
        Show nested call depth with tree lines.
    logger_name / log_dir : str | None
        Override logger name or log directory.
    deep_trace : bool
        ``True`` (default): trace line-by-line, sub-calls, awaits,
        and local variable snapshots.
        ``False``: lightweight mode — only log entry/exit.
    """
    _ignore = ignore_methods or set()
    if cls is not None:
        return _apply_tracker(cls, level, max_str_len, log_result, log_args,
                              _ignore, indent, logger_name, log_dir, deep_trace)

    def decorator(klass: Type[T]) -> Type[T]:
        return _apply_tracker(klass, level, max_str_len, log_result, log_args,
                              _ignore, indent, logger_name, log_dir, deep_trace)
    return decorator
