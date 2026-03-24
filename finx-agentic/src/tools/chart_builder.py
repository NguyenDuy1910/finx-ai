"""Chart builder toolkit — the LLM calls build_chart_spec to emit a chart spec."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from agno.tools import Toolkit

log = logging.getLogger(__name__)


class ChartBuilderTools(Toolkit):
    """Provides the build_chart_spec tool that the Chart Builder Agent calls
    to return a structured chart/dashboard specification to the frontend."""

    def __init__(self) -> None:
        super().__init__(
            name="chart_builder_tools",
            tools=[self.build_chart_spec],
        )

    def build_chart_spec(self, spec: str) -> str:
        """Emit a chart specification that the frontend will render.

        Call this tool ONCE per turn with the full chart specification as a
        JSON string. The spec must follow the schema described in your
        instructions (chart_type, title, x_axis, y_axis, series, data, etc.).

        Args:
            spec: Chart specification as a JSON string matching the required schema.

        Returns:
            The validated chart spec JSON string ready for the frontend.
        """
        # Validate that spec is parseable JSON
        try:
            parsed: Dict[str, Any] = json.loads(spec) if isinstance(spec, str) else spec
        except (json.JSONDecodeError, TypeError) as exc:
            log.warning("build_chart_spec received invalid JSON: %s", exc)
            return json.dumps({"error": f"Invalid chart spec JSON: {exc}", "raw": str(spec)})

        chart_type = parsed.get("chart_type", "unknown")
        log.info("Chart spec built: type=%s, title=%s", chart_type, parsed.get("title", ""))

        # Return canonical JSON (ensures consistent serialisation for the frontend)
        return json.dumps(parsed, ensure_ascii=False)
