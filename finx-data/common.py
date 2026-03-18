"""common.py — 9Router LLM client + output writer.

All route scripts import from here:
  from common import llm, extract, async_extract, save, log
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI
from rich.logging import RichHandler

load_dotenv()

# ── logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
log = logging.getLogger("finx-data")

# ── 9Router LLM clients (sync + async) ───────────────────────────────────────

_base_url = os.getenv("NINE_ROUTER_BASE_URL", "http://localhost:20128/v1")
_api_key  = os.getenv("NINE_ROUTER_API_KEY", "YOUR_9ROUTER_KEY")
MODEL     = os.getenv("NINE_ROUTER_MODEL", "default")

# Sync client — kept for backward compatibility with any direct llm.* calls
llm = OpenAI(base_url=_base_url, api_key=_api_key)

# Async client — used by async_extract()
_async_llm = AsyncOpenAI(base_url=_base_url, api_key=_api_key)

# ── output dir ────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── core helpers ──────────────────────────────────────────────────────────────

def extract(prompt: str, system: str = "", *, model: str | None = None) -> dict | list:
    """Send text to 9Router synchronously, get structured JSON back.
    Kept for scripts that don't use the async loop."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = llm.chat.completions.create(
        model=model or MODEL,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)


async def async_extract(
    prompt: str,
    system: str = "",
    *,
    model: str | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> dict | list:
    """Send text to 9Router asynchronously, get structured JSON back.

    Parameters
    ----------
    prompt    : user message content
    system    : system prompt string
    model     : override the MODEL env var
    semaphore : optional asyncio.Semaphore to cap concurrent in-flight requests
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async def _call() -> dict | list:
        resp = await _async_llm.chat.completions.create(
            model=model or MODEL,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        return json.loads(raw)

    if semaphore:
        async with semaphore:
            return await _call()
    return await _call()


def save(route: str, name: str, data: dict | list) -> Path:
    """Save a structured record to output/<route>/<name>.json."""
    route_dir = OUTPUT_DIR / route
    route_dir.mkdir(parents=True, exist_ok=True)

    # slugify name
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    path = route_dir / f"{safe_name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    log.debug("Saved %s", path)
    return path


def save_batch(route: str, items: list[dict]) -> int:
    """Save a list of structured records, returns count saved."""
    count = 0
    for item in items:
        name = (
            item.get("name")
            or item.get("table_name")
            or item.get("term")
            or item.get("question")
            or item.get("policy_name")
            or item.get("feedback_id")
            or f"item_{count}"
        )
        save(route, str(name), item)
        count += 1
    return count


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
