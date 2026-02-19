"use client";

import { useState } from "react";
import {
  BarChart3,
  ChevronDown,
  Timer,
  Cpu,
  Brain,
  Eye,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { RunMetrics } from "@/types";

interface RunMetricsBlockProps {
  metrics: RunMetrics;
}

export function RunMetricsBlock({ metrics }: RunMetricsBlockProps) {
  const [expanded, setExpanded] = useState(false);

  const hasData =
    metrics.total_tokens ||
    metrics.input_tokens ||
    metrics.output_tokens ||
    metrics.time_to_first_token;

  if (!hasData) return null;

  // Compact inline summary
  const summaryParts: string[] = [];
  if (metrics.total_tokens)
    summaryParts.push(`${metrics.total_tokens.toLocaleString()} tokens`);
  if (metrics.time_to_first_token)
    summaryParts.push(`${metrics.time_to_first_token.toFixed(0)}ms TTFT`);

  return (
    <div className="overflow-hidden rounded-xl border border-border/20 bg-gradient-to-r from-muted/20 to-transparent transition-all">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-muted/20"
        aria-expanded={expanded}
        aria-label="Run metrics"
      >
        <BarChart3 className="h-3 w-3 shrink-0 text-primary/30" />
        <span className="flex-1 text-[10px] text-muted-foreground/50">
          {summaryParts.join(" · ") || "Run metrics"}
        </span>
        {expanded ? (
          <ChevronDown className="h-3 w-3 text-muted-foreground/30" />
        ) : (
          <Eye className="h-2.5 w-2.5 text-muted-foreground/30" />
        )}
      </button>

      {expanded && (
        <div className="animate-fade-in border-t border-border/10 px-3 py-2">
          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-4">
            {metrics.input_tokens != null && (
              <MetricItem
                icon={<Cpu className="h-3 w-3" />}
                label="Input"
                value={metrics.input_tokens.toLocaleString()}
                unit="tokens"
              />
            )}
            {metrics.output_tokens != null && (
              <MetricItem
                icon={<Cpu className="h-3 w-3" />}
                label="Output"
                value={metrics.output_tokens.toLocaleString()}
                unit="tokens"
              />
            )}
            {metrics.reasoning_tokens != null && metrics.reasoning_tokens > 0 && (
              <MetricItem
                icon={<Brain className="h-3 w-3" />}
                label="Reasoning"
                value={metrics.reasoning_tokens.toLocaleString()}
                unit="tokens"
              />
            )}
            {metrics.time_to_first_token != null && (
              <MetricItem
                icon={<Timer className="h-3 w-3" />}
                label="TTFT"
                value={`${metrics.time_to_first_token.toFixed(0)}`}
                unit="ms"
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricItem({
  icon,
  label,
  value,
  unit,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-muted-foreground/40">{icon}</span>
      <div className="flex items-baseline gap-1">
        <span className="text-[10px] text-muted-foreground/50">{label}</span>
        <span className="text-[11px] font-medium tabular-nums text-foreground/70">
          {value}
        </span>
        <span className="text-[10px] text-muted-foreground/40">{unit}</span>
      </div>
    </div>
  );
}
