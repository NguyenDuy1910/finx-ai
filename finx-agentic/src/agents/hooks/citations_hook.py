"""Post-hook that strips technical retrieval tags and appends a <citations> block for the frontend."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from agno.agent import Agent

from src.knowledge.retrieval.utils.citations import CITATIONS_STATE_KEY

log = logging.getLogger(__name__)

_TECHNICAL_TAGS = re.compile(
    r"<retrieval-citations>.*?</retrieval-citations>"
    r"|<tool[^>]*>.*?</tool>"
    r"|<search[_-]result[^>]*>.*?</search[_-]result>",
    re.DOTALL | re.IGNORECASE,
)


def _extract_content_str(run_output: Any) -> Optional[str]:
    """Return the response text as a str, or None if unavailable."""
    content = run_output.content
    if isinstance(content, str):
        return content
    if content is None:
        # Some model responses store text only in messages; try the last assistant message.
        messages = getattr(run_output, "messages", None) or []
        for msg in reversed(messages):
            role = getattr(msg, "role", None)
            text = getattr(msg, "content", None)
            if role == "assistant" and isinstance(text, str) and text.strip():
                return text
        return None
    # Structured output or list — not text, skip citation injection.
    return None


def _collect_citations(
    agent: Agent,
    run_context: Any,
) -> List[Dict[str, Any]]:
    """Pull accumulated citations from the best available session-state source.

    Priority:
      1. run_context.session_state  — per-request state managed by the Agno run
      2. agent.session_state        — singleton shared state (legacy fallback)
    """
    # 1. Per-request state (preferred — no cross-request bleed)
    rc_state: Optional[Dict[str, Any]] = None
    if run_context is not None:
        rc_state = getattr(run_context, "session_state", None)
    if rc_state and rc_state.get(CITATIONS_STATE_KEY):
        log.debug("[citations_hook] reading citations from run_context.session_state")
        return list(rc_state.get(CITATIONS_STATE_KEY) or [])

    # 2. Agent session_state (writes from knowledge.session_state → shared_state)
    agent_state: Optional[Dict[str, Any]] = getattr(agent, "session_state", None)
    if agent_state:
        log.debug("[citations_hook] reading citations from agent.session_state")
        return list(agent_state.get(CITATIONS_STATE_KEY) or [])

    return []


def _clear_citations(agent: Agent, run_context: Any) -> None:
    """Remove citations from all session-state sources after consumption."""
    rc_state: Optional[Dict[str, Any]] = None
    if run_context is not None:
        rc_state = getattr(run_context, "session_state", None)
    if rc_state is not None:
        rc_state[CITATIONS_STATE_KEY] = []

    agent_state: Optional[Dict[str, Any]] = getattr(agent, "session_state", None)
    if agent_state is not None:
        agent_state[CITATIONS_STATE_KEY] = []


def emit_citations_hook(
    run_output: Any,
    agent: Agent,
    run_context: Any = None,
) -> None:
    """Strip technical noise, then append ``<citations>`` JSON for the UI.

    Accepts ``run_context`` (injected by Agno) to enable per-request citation
    scoping and avoid cross-request bleed when multiple sessions share the
    same agent instance.
    """
    content = _extract_content_str(run_output)
    if content is None:
        log.debug(
            "[citations_hook] run_output.content is %r — skipping citation injection",
            type(run_output.content).__name__,
        )
        return

    cleaned = _TECHNICAL_TAGS.sub("", content).strip()

    citations = _collect_citations(agent, run_context)
    valid = [c for c in citations if c.get("title") or c.get("snippet")]

    if valid:
        try:
            citations_json = json.dumps(valid, ensure_ascii=False, default=str)
        except Exception as exc:
            log.warning("[citations_hook] json.dumps failed (%s) — omitting citations block", exc)
            run_output.content = cleaned
            _clear_citations(agent, run_context)
            return

        run_output.content = cleaned + f"\n\n<citations>{citations_json}</citations>"
        log.debug("[citations_hook] appended %d citations", len(valid))
    else:
        run_output.content = cleaned
        if citations:
            log.debug(
                "[citations_hook] %d citation(s) had no title/snippet — discarded",
                len(citations),
            )

    _clear_citations(agent, run_context)

