from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_initialized = False


def init_agentops(
    api_key: Optional[str] = None,
    auto_start_session: bool = True,
    tags: Optional[List[str]] = None,
    trace_name: Optional[str] = None,
    **kwargs: Any,
) -> bool:
    
    global _initialized
    if _initialized:
        logger.debug("AgentOps already initialised – skipping")
        return True

    resolved_key = api_key or os.getenv("AGENTOPS_API_KEY")
    if not resolved_key:
        logger.warning(
            "AGENTOPS_API_KEY not set – AgentOps observability is disabled. "
            "Get your key from https://app.agentops.ai/settings/projects"
        )
        return False

    try:
        import agentops.instrumentation as _ao_inst
        _ao_inst.AGENTIC_LIBRARIES.pop("agno", None)
        _ao_inst.TARGET_PACKAGES.discard("agno")

        import agentops

        init_kwargs: Dict[str, Any] = {
            "api_key": resolved_key,
            "auto_start_session": auto_start_session,
            "default_tags": tags or ["finx-agentic"],
        }
        if trace_name:
            init_kwargs["trace_name"] = trace_name

        init_kwargs.update(kwargs)
        agentops.init(**init_kwargs)

        _initialized = True
        logger.info("AgentOps initialised successfully")
        return True

    except Exception as exc:
        logger.error(f"Failed to initialise AgentOps: {exc}")
        return False


def end_session(
    end_state: str = "Success",
    end_state_reason: Optional[str] = None,
) -> None:
    """End the current AgentOps session gracefully."""
    if not _initialized:
        return
    try:
        import agentops
        agentops.end_session(end_state=end_state, end_state_reason=end_state_reason)
        logger.info(f"AgentOps session ended – state={end_state}")
    except Exception as exc:
        logger.warning(f"Failed to end AgentOps session: {exc}")


def start_trace(
    name: str,
    tags: Optional[List[str]] = None,
) -> Any:
    """Manually start an AgentOps trace (for advanced usage)."""
    if not _initialized:
        return None
    try:
        import agentops
        return agentops.start_trace(name=name, tags=tags)
    except Exception as exc:
        logger.warning(f"Failed to start AgentOps trace: {exc}")
        return None


def end_trace(
    trace: Any,
    end_state: str = "Success",
    error_message: Optional[str] = None,
) -> None:
    """Manually end an AgentOps trace."""
    if not _initialized or trace is None:
        return
    try:
        import agentops
        kwargs: Dict[str, Any] = {"end_state": end_state}
        if error_message:
            kwargs["error_message"] = error_message
        agentops.end_trace(trace, **kwargs)
    except Exception as exc:
        logger.warning(f"Failed to end AgentOps trace: {exc}")


def update_trace_metadata(metadata: Dict[str, Any]) -> None:
    """Update metadata on the currently running trace."""
    if not _initialized:
        return
    try:
        from agentops import update_trace_metadata as _update
        _update(metadata)
    except Exception as exc:
        logger.warning(f"Failed to update AgentOps trace metadata: {exc}")


# ── Re-export decorators for convenience ──────────────────────────────
# These are thin wrappers so that the rest of the codebase can import from
# a single location: ``from src.core.agentops_tracker import trace, agent, ...``


def _noop_decorator(*args, **kwargs):
    """Fallback no-op decorator when AgentOps is not available."""
    if args and callable(args[0]):
        return args[0]

    def wrapper(fn):
        return fn

    return wrapper


try:
    from agentops.sdk.decorators import trace, agent, operation, tool
except ImportError:
    # Graceful degradation when agentops is not installed
    trace = _noop_decorator      # type: ignore[assignment]
    agent = _noop_decorator      # type: ignore[assignment]
    operation = _noop_decorator   # type: ignore[assignment]
    tool = _noop_decorator        # type: ignore[assignment]
    logger.debug("agentops decorators not available – using no-op fallbacks")
