import json
import logging
from typing import Any, Dict, List, Optional

from agno.tools import Toolkit

logger = logging.getLogger(__name__)


class ChartBuilderTools(Toolkit):
    """Tools for the Chart Builder Agent to produce chart specifications."""

    def __init__(self, **kwargs):
        tools: List[Any] = [
            self.build_chart_spec,
        ]
        super().__init__(name="chart_builder_tools", tools=tools, **kwargs)

    def build_chart_spec(
        self,
        chart_type: str,
        title: str,
        data: List[Dict[str, Any]],
        x_axis: Optional[Dict[str, str]] = None,
        y_axis: Optional[Dict[str, str]] = None,
        series: Optional[List[Dict[str, str]]] = None,
        subtitle: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        insights: Optional[List[str]] = None,
    ) -> str:
        """Build a chart specification from SQL query results.

        Args:
            chart_type: The type of chart — one of: bar, horizontal_bar, line,
                area, pie, donut, stacked_bar, grouped_bar, scatter, table,
                metric, multi_metric.
            title: A human-readable title for the chart.
            data: The chart data as a list of row dicts.
            x_axis: X-axis config with keys: field, label, type (category|datetime|numeric).
            y_axis: Y-axis config with keys: field, label, format (number|currency|percent).
            series: List of series dicts with keys: name, field, color (optional).
            subtitle: Optional subtitle or date range context.
            options: Display options like show_legend, show_grid, sort_by, color_palette, etc.
            insights: List of 1-3 key data insights.

        Returns:
            JSON string of the chart specification.
        """
        valid_types = {
            "bar", "horizontal_bar", "line", "area", "pie", "donut",
            "stacked_bar", "grouped_bar", "scatter", "table",
            "metric", "multi_metric",
        }

        if chart_type not in valid_types:
            return json.dumps({
                "error": f"Invalid chart_type '{chart_type}'. Must be one of: {', '.join(sorted(valid_types))}"
            })

        if not data:
            return json.dumps({
                "error": "No data provided for chart. Cannot build visualization."
            })

        # Limit data rows to prevent oversized payloads
        max_rows = 500
        truncated = False
        if len(data) > max_rows:
            data = data[:max_rows]
            truncated = True

        spec: Dict[str, Any] = {
            "chart_type": chart_type,
            "title": title,
        }

        if subtitle:
            spec["subtitle"] = subtitle

        if x_axis:
            spec["x_axis"] = x_axis

        if y_axis:
            spec["y_axis"] = y_axis

        if series:
            spec["series"] = series

        spec["data"] = data
        spec["row_count"] = len(data)

        if truncated:
            spec["truncated"] = True
            spec["truncated_message"] = f"Showing first {max_rows} of total rows."

        if options:
            spec["options"] = options
        else:
            spec["options"] = {
                "show_legend": len(series or []) > 1,
                "show_grid": chart_type in {"bar", "horizontal_bar", "line", "area", "scatter", "grouped_bar", "stacked_bar"},
                "show_values": len(data) <= 20,
                "color_palette": "banking",
            }

        if insights:
            spec["insights"] = insights

        logger.info(
            "Chart spec built: type=%s, title=%s, rows=%d",
            chart_type, title, len(data),
        )

        return json.dumps(spec, default=str, ensure_ascii=False)
