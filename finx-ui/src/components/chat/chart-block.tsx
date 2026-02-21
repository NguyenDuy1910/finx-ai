"use client";

import { useState, useMemo } from "react";
import {
  BarChart3,
  PieChart,
  TrendingUp,
  TrendingDown,
  Minus,
  Table2,
  ChevronDown,
  ChevronUp,
  Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface ChartAxisConfig {
  field: string;
  label: string;
  type?: "category" | "datetime" | "numeric";
  format?: "number" | "currency" | "percent";
}

export interface ChartSeries {
  name: string;
  field: string;
  color?: string;
}

export interface ChartMetricItem {
  label: string;
  value: string;
  raw_value?: number;
  change?: number;
  change_direction?: "up" | "down" | "neutral";
}

export interface ChartOptions {
  show_legend?: boolean;
  show_grid?: boolean;
  show_values?: boolean;
  sort_by?: string | null;
  sort_order?: "asc" | "desc";
  limit?: number | null;
  color_palette?: "default" | "banking" | "warm" | "cool";
}

export interface ChartSpec {
  chart_type: string;
  title: string;
  subtitle?: string;
  x_axis?: ChartAxisConfig;
  y_axis?: ChartAxisConfig;
  series?: ChartSeries[];
  data: Record<string, unknown>[];
  row_count?: number;
  truncated?: boolean;
  truncated_message?: string;
  options?: ChartOptions;
  insights?: string[];
}

/* ------------------------------------------------------------------ */
/*  Color palettes                                                     */
/* ------------------------------------------------------------------ */

const PALETTES: Record<string, string[]> = {
  default: [
    "#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ef4444",
    "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#3b82f6",
  ],
  banking: [
    "#1e40af", "#2563eb", "#3b82f6", "#60a5fa", "#93c5fd",
    "#059669", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  ],
  warm: [
    "#dc2626", "#ea580c", "#d97706", "#ca8a04", "#65a30d",
    "#f43f5e", "#fb923c", "#fbbf24", "#a3e635", "#4ade80",
  ],
  cool: [
    "#1d4ed8", "#2563eb", "#0891b2", "#0d9488", "#059669",
    "#6366f1", "#06b6d4", "#14b8a6", "#10b981", "#22c55e",
  ],
};

function getColors(palette?: string): string[] {
  return PALETTES[palette || "banking"] || PALETTES.banking;
}

/* ------------------------------------------------------------------ */
/*  Utilities                                                          */
/* ------------------------------------------------------------------ */

function formatNumber(val: unknown): string {
  const n = Number(val);
  if (isNaN(n)) return String(val ?? "");
  if (Math.abs(n) >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + "B";
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n % 1 === 0 ? n.toLocaleString() : n.toFixed(2);
}

function truncateLabel(label: string, maxLen = 14): string {
  if (label.length <= maxLen) return label;
  return label.slice(0, maxLen - 1) + "…";
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function ChartHeader({
  title,
  subtitle,
  chartType,
}: {
  title: string;
  subtitle?: string;
  chartType: string;
}) {
  const Icon =
    chartType === "pie" || chartType === "donut"
      ? PieChart
      : chartType === "table"
        ? Table2
        : BarChart3;

  return (
    <div className="flex items-start justify-between px-4 pt-4 pb-2">
      <div className="space-y-0.5">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary/70" />
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        </div>
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </div>
      <Badge variant="default" className="text-[10px] shrink-0">
        {chartType.replace("_", " ")}
      </Badge>
    </div>
  );
}

function InsightsSection({ insights }: { insights: string[] }) {
  return (
    <div className="border-t border-border/50 px-4 py-3">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
        Insights
      </p>
      <ul className="space-y-1">
        {insights.map((insight, i) => (
          <li key={i} className="flex items-start gap-1.5 text-xs text-foreground/80">
            <span className="mt-0.5 text-primary">•</span>
            {insight}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Metric chart                                                       */
/* ------------------------------------------------------------------ */

function MetricChart({ spec }: { spec: ChartSpec }) {
  const items = spec.data as unknown as ChartMetricItem[];

  return (
    <div className={cn(
      "grid gap-4 px-4 py-4",
      items.length === 1 ? "grid-cols-1" : items.length === 2 ? "grid-cols-2" : "grid-cols-2 lg:grid-cols-4"
    )}>
      {items.map((item, i) => {
        const DirIcon = item.change_direction === "up"
          ? TrendingUp
          : item.change_direction === "down"
            ? TrendingDown
            : Minus;

        const dirColor = item.change_direction === "up"
          ? "text-emerald-500"
          : item.change_direction === "down"
            ? "text-red-500"
            : "text-muted-foreground";

        return (
          <div
            key={i}
            className="rounded-xl border border-border/50 bg-gradient-to-br from-muted/30 to-transparent p-4 text-center"
          >
            <p className="text-xs text-muted-foreground mb-1">{item.label}</p>
            <p className="text-2xl font-bold text-foreground">{item.value}</p>
            {item.change != null && (
              <div className={cn("mt-1.5 flex items-center justify-center gap-1 text-xs", dirColor)}>
                <DirIcon className="h-3 w-3" />
                <span>{item.change > 0 ? "+" : ""}{item.change}%</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Bar chart (vertical / horizontal)                                  */
/* ------------------------------------------------------------------ */

function BarChart({
  spec,
  horizontal = false,
}: {
  spec: ChartSpec;
  horizontal?: boolean;
}) {
  const colors = getColors(spec.options?.color_palette);
  const xField = spec.x_axis?.field || "";
  const yField = spec.y_axis?.field || spec.series?.[0]?.field || "";

  const values = spec.data.map((d) => Number(d[yField]) || 0);
  const maxVal = Math.max(...values, 1);

  if (horizontal) {
    return (
      <div className="px-4 py-3 space-y-2">
        {spec.data.map((row, i) => {
          const label = String(row[xField] ?? "");
          const val = Number(row[yField]) || 0;
          const pct = (val / maxVal) * 100;
          return (
            <div key={i} className="flex items-center gap-2">
              <span className="w-28 truncate text-right text-xs text-muted-foreground" title={label}>
                {truncateLabel(label)}
              </span>
              <div className="flex-1 h-6 rounded-md bg-muted/40 overflow-hidden relative">
                <div
                  className="h-full rounded-md transition-all duration-500"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: colors[i % colors.length],
                  }}
                />
                {spec.options?.show_values && (
                  <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-medium text-foreground/70">
                    {formatNumber(val)}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  // Vertical bar chart
  const barWidth = Math.max(20, Math.min(60, 500 / spec.data.length));
  const chartHeight = 200;

  return (
    <div className="px-4 py-3 overflow-x-auto">
      <div className="flex items-end gap-1 justify-center" style={{ minHeight: chartHeight + 40 }}>
        {spec.data.map((row, i) => {
          const label = String(row[xField] ?? "");
          const val = Number(row[yField]) || 0;
          const barHeight = (val / maxVal) * chartHeight;
          return (
            <div key={i} className="flex flex-col items-center gap-1" style={{ width: barWidth }}>
              {spec.options?.show_values && (
                <span className="text-[9px] text-muted-foreground whitespace-nowrap">
                  {formatNumber(val)}
                </span>
              )}
              <div
                className="w-full rounded-t-md transition-all duration-500 hover:opacity-80 cursor-default"
                style={{
                  height: barHeight,
                  backgroundColor: colors[i % colors.length],
                }}
                title={`${label}: ${formatNumber(val)}`}
              />
              <span
                className="text-[9px] text-muted-foreground text-center leading-tight break-words"
                style={{ maxWidth: barWidth }}
                title={label}
              >
                {truncateLabel(label, 8)}
              </span>
            </div>
          );
        })}
      </div>
      {/* Axis labels */}
      <div className="flex justify-between mt-2 px-2">
        {spec.x_axis?.label && (
          <span className="text-[10px] text-muted-foreground/60">{spec.x_axis.label}</span>
        )}
        {spec.y_axis?.label && (
          <span className="text-[10px] text-muted-foreground/60">{spec.y_axis.label}</span>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Line / Area chart                                                  */
/* ------------------------------------------------------------------ */

function LineAreaChart({
  spec,
  isArea = false,
}: {
  spec: ChartSpec;
  isArea?: boolean;
}) {
  const colors = getColors(spec.options?.color_palette);
  const xField = spec.x_axis?.field || "";
  const yField = spec.y_axis?.field || spec.series?.[0]?.field || "";

  const dataPoints = spec.data.map((d) => ({
    label: String(d[xField] ?? ""),
    value: Number(d[yField]) || 0,
  }));

  const values = dataPoints.map((d) => d.value);
  const maxVal = Math.max(...values, 1);
  const minVal = Math.min(...values, 0);
  const range = maxVal - minVal || 1;

  const svgWidth = 600;
  const svgHeight = 200;
  const padding = { top: 20, right: 20, bottom: 40, left: 50 };
  const plotW = svgWidth - padding.left - padding.right;
  const plotH = svgHeight - padding.top - padding.bottom;

  const points = dataPoints.map((d, i) => ({
    x: padding.left + (i / Math.max(dataPoints.length - 1, 1)) * plotW,
    y: padding.top + plotH - ((d.value - minVal) / range) * plotH,
    ...d,
  }));

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const areaPath = linePath + ` L ${points[points.length - 1]?.x ?? 0} ${padding.top + plotH} L ${points[0]?.x ?? 0} ${padding.top + plotH} Z`;

  // Y-axis ticks
  const yTicks = 5;
  const yTickValues = Array.from({ length: yTicks }, (_, i) => minVal + (range * i) / (yTicks - 1));

  return (
    <div className="px-4 py-3 overflow-x-auto">
      <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="w-full" style={{ maxHeight: 250 }}>
        {/* Grid lines */}
        {spec.options?.show_grid !== false &&
          yTickValues.map((tv, i) => {
            const y = padding.top + plotH - ((tv - minVal) / range) * plotH;
            return (
              <g key={i}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={svgWidth - padding.right}
                  y2={y}
                  stroke="currentColor"
                  strokeOpacity={0.08}
                  strokeDasharray="4 4"
                />
                <text
                  x={padding.left - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-muted-foreground"
                  fontSize={9}
                >
                  {formatNumber(tv)}
                </text>
              </g>
            );
          })}

        {/* Area fill */}
        {isArea && points.length > 1 && (
          <path d={areaPath} fill={colors[0]} fillOpacity={0.15} />
        )}

        {/* Line */}
        {points.length > 1 && (
          <path d={linePath} fill="none" stroke={colors[0]} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
        )}

        {/* Dots */}
        {points.map((p, i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={3.5} fill={colors[0]} />
            {spec.options?.show_values && (
              <text x={p.x} y={p.y - 8} textAnchor="middle" className="fill-foreground" fontSize={8} fontWeight={500}>
                {formatNumber(p.value)}
              </text>
            )}
          </g>
        ))}

        {/* X-axis labels */}
        {points.map((p, i) => {
          // Show limited labels to avoid overlap
          const step = Math.max(1, Math.floor(points.length / 8));
          if (i % step !== 0 && i !== points.length - 1) return null;
          return (
            <text
              key={i}
              x={p.x}
              y={svgHeight - padding.bottom + 16}
              textAnchor="middle"
              className="fill-muted-foreground"
              fontSize={8}
            >
              {truncateLabel(p.label, 10)}
            </text>
          );
        })}
      </svg>

      <div className="flex justify-between mt-1 px-2">
        {spec.x_axis?.label && (
          <span className="text-[10px] text-muted-foreground/60">{spec.x_axis.label}</span>
        )}
        {spec.y_axis?.label && (
          <span className="text-[10px] text-muted-foreground/60">{spec.y_axis.label}</span>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Pie / Donut chart                                                  */
/* ------------------------------------------------------------------ */

function PieDonutChart({
  spec,
  isDonut = false,
}: {
  spec: ChartSpec;
  isDonut?: boolean;
}) {
  const colors = getColors(spec.options?.color_palette);
  const xField = spec.x_axis?.field || "";
  const yField = spec.y_axis?.field || spec.series?.[0]?.field || "";

  const slices = spec.data.map((d) => ({
    label: String(d[xField] ?? ""),
    value: Math.max(0, Number(d[yField]) || 0),
  }));

  const total = slices.reduce((s, d) => s + d.value, 0) || 1;

  const cx = 120;
  const cy = 120;
  const r = 100;
  const innerR = isDonut ? 55 : 0;

  let cumAngle = -Math.PI / 2;

  const paths = slices.map((slice, i) => {
    const angle = (slice.value / total) * 2 * Math.PI;
    const startAngle = cumAngle;
    const endAngle = cumAngle + angle;
    cumAngle = endAngle;

    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);

    const ix1 = cx + innerR * Math.cos(startAngle);
    const iy1 = cy + innerR * Math.sin(startAngle);
    const ix2 = cx + innerR * Math.cos(endAngle);
    const iy2 = cy + innerR * Math.sin(endAngle);

    const largeArc = angle > Math.PI ? 1 : 0;

    const d = innerR > 0
      ? `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} L ${ix2} ${iy2} A ${innerR} ${innerR} 0 ${largeArc} 0 ${ix1} ${iy1} Z`
      : `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`;

    return { d, color: colors[i % colors.length], label: slice.label, value: slice.value, pct: ((slice.value / total) * 100).toFixed(1) };
  });

  return (
    <div className="px-4 py-3 flex flex-col sm:flex-row items-center gap-4">
      <svg viewBox="0 0 240 240" className="w-48 h-48 shrink-0">
        {paths.map((p, i) => (
          <path
            key={i}
            d={p.d}
            fill={p.color}
            stroke="white"
            strokeWidth={2}
            className="hover:opacity-80 transition-opacity cursor-default"
          >
            <title>{`${p.label}: ${formatNumber(p.value)} (${p.pct}%)`}</title>
          </path>
        ))}
        {isDonut && (
          <text x={cx} y={cy + 4} textAnchor="middle" className="fill-foreground text-sm font-bold" fontSize={14}>
            {formatNumber(total)}
          </text>
        )}
      </svg>

      {/* Legend */}
      <div className="space-y-1.5 min-w-0">
        {paths.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 rounded-sm shrink-0" style={{ backgroundColor: p.color }} />
            <span className="text-foreground/80 truncate">{p.label}</span>
            <span className="text-muted-foreground ml-auto whitespace-nowrap">{p.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Data table                                                         */
/* ------------------------------------------------------------------ */

function DataTable({ spec }: { spec: ChartSpec }) {
  const [showAll, setShowAll] = useState(false);
  const limit = 10;
  const rows = showAll ? spec.data : spec.data.slice(0, limit);
  const columns = spec.data.length > 0 ? Object.keys(spec.data[0]) : [];

  return (
    <div className="px-4 py-3">
      <div className="overflow-x-auto rounded-lg border border-border/50">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border/50 bg-muted/30">
              {columns.map((col) => (
                <th key={col} className="px-3 py-2 text-left font-semibold text-muted-foreground whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-border/20 hover:bg-muted/20 transition-colors">
                {columns.map((col) => (
                  <td key={col} className="px-3 py-1.5 text-foreground/80 whitespace-nowrap">
                    {String(row[col] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {spec.data.length > limit && (
        <button
          type="button"
          onClick={() => setShowAll(!showAll)}
          className="mt-2 flex items-center gap-1 text-xs text-primary hover:underline"
        >
          {showAll ? (
            <>
              <ChevronUp className="h-3 w-3" /> Show less
            </>
          ) : (
            <>
              <ChevronDown className="h-3 w-3" /> Show all {spec.data.length} rows
            </>
          )}
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main ChartBlock component                                          */
/* ------------------------------------------------------------------ */

interface ChartBlockProps {
  spec: ChartSpec;
}

export function ChartBlock({ spec }: ChartBlockProps) {
  const [viewMode, setViewMode] = useState<"chart" | "table">("chart");

  const canToggle = spec.chart_type !== "table" && spec.chart_type !== "metric" && spec.chart_type !== "multi_metric";

  const chartContent = useMemo(() => {
    if (viewMode === "table" && canToggle) {
      return <DataTable spec={spec} />;
    }

    switch (spec.chart_type) {
      case "metric":
      case "multi_metric":
        return <MetricChart spec={spec} />;
      case "bar":
        return <BarChart spec={spec} />;
      case "horizontal_bar":
        return <BarChart spec={spec} horizontal />;
      case "grouped_bar":
      case "stacked_bar":
        return <BarChart spec={spec} />;
      case "line":
        return <LineAreaChart spec={spec} />;
      case "area":
        return <LineAreaChart spec={spec} isArea />;
      case "pie":
        return <PieDonutChart spec={spec} />;
      case "donut":
        return <PieDonutChart spec={spec} isDonut />;
      case "scatter":
        return <LineAreaChart spec={spec} />;
      case "table":
      default:
        return <DataTable spec={spec} />;
    }
  }, [spec, viewMode, canToggle]);

  return (
    <Card className="mt-3 overflow-hidden border-primary/10">
      <ChartHeader
        title={spec.title}
        subtitle={spec.subtitle}
        chartType={spec.chart_type}
      />

      {/* Toggle chart / table view */}
      {canToggle && (
        <div className="flex items-center gap-1 px-4 pb-1">
          <button
            type="button"
            onClick={() => setViewMode("chart")}
            className={cn(
              "rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors",
              viewMode === "chart"
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <BarChart3 className="h-3 w-3 inline mr-1" />
            Chart
          </button>
          <button
            type="button"
            onClick={() => setViewMode("table")}
            className={cn(
              "rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors",
              viewMode === "table"
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Table2 className="h-3 w-3 inline mr-1" />
            Table
          </button>
        </div>
      )}

      {chartContent}

      {/* Truncation warning */}
      {spec.truncated && spec.truncated_message && (
        <div className="border-t border-border/50 px-4 py-2">
          <p className="text-[10px] text-yellow-600 dark:text-yellow-400">
            ⚠ {spec.truncated_message}
          </p>
        </div>
      )}

      {/* Insights */}
      {spec.insights && spec.insights.length > 0 && (
        <InsightsSection insights={spec.insights} />
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Parser utility: extract chart spec from tool call results          */
/* ------------------------------------------------------------------ */

export function parseChartSpecFromToolCalls(
  toolCalls?: { name: string; result?: string }[]
): ChartSpec | null {
  if (!toolCalls) return null;

  for (const tc of toolCalls) {
    if (tc.name === "build_chart_spec" && tc.result) {
      try {
        const parsed = JSON.parse(tc.result);
        if (parsed.chart_type && parsed.data) {
          return parsed as ChartSpec;
        }
      } catch {
        // ignore parse errors
      }
    }
  }

  return null;
}
