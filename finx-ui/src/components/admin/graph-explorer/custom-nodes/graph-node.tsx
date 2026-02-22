"use client";

import { memo, useCallback, useMemo } from "react";
import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import { Plus, Minus, Loader2 } from "lucide-react";
import { useGraphContext } from "../graph-context";

interface GraphNodeData {
  label: string;
  nodeLabel: string;
  summary: string;
  color: string;
  attributes: Record<string, unknown>;
  [key: string]: unknown;
}

/** Estimate a reasonable node width (px) from text content */
function estimateWidth(label: string, summary: string): number {
  const longest = Math.max(label.length, summary.length);
  // ~7px per char at text-sm, plus 24px horizontal padding + 24px for expand btn
  const estimated = Math.ceil(longest * 7) + 48;
  // Clamp between 160 and 320
  return Math.max(160, Math.min(320, estimated));
}

function GraphNodeComponent({ id, data, selected }: NodeProps) {
  const {
    label,
    nodeLabel,
    summary,
    color,
  } = data as unknown as GraphNodeData;

  const { expandedNodes, loadingNodes, onExpandNode, onCollapseNode } = useGraphContext();
  const expanded = expandedNodes.has(id);
  const childrenLoading = loadingNodes.has(id);

  const width = useMemo(
    () => estimateWidth(label as string, (summary as string) || ""),
    [label, summary]
  );

  const handleToggle = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (childrenLoading) return;
      if (expanded) {
        onCollapseNode(id);
      } else {
        onExpandNode(id);
      }
    },
    [id, expanded, childrenLoading, onExpandNode, onCollapseNode]
  );

  return (
    <div
      className={`group relative rounded-lg border-2 bg-background px-3 py-2 shadow-sm transition-all hover:shadow-md ${selected ? "shadow-md ring-2 ring-ring" : ""}`}
      style={{ borderColor: color as string, width }}
    >
      <Handle type="target" position={Position.Top} className="!bg-muted-foreground" />
      <div className="flex items-center gap-2">
        <div className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: color as string }} />
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground truncate">
          {nodeLabel as string}
        </span>
      </div>
      <div className="mt-1 text-sm font-semibold pr-6 break-words leading-tight">
        {label as string}
      </div>
      {summary && (
        <div className="mt-0.5 text-[11px] text-muted-foreground pr-6 line-clamp-2 leading-tight">
          {summary as string}
        </div>
      )}

      {/* Expand / Collapse toggle button */}
      <button
        onClick={handleToggle}
        className={`absolute -bottom-3 left-1/2 -translate-x-1/2 z-10 flex h-6 w-6 items-center justify-center rounded-full border-2 bg-background shadow-sm transition-all hover:scale-110 ${
          expanded
            ? "border-orange-400 text-orange-500 hover:bg-orange-50 dark:hover:bg-orange-950"
            : "border-emerald-400 text-emerald-500 hover:bg-emerald-50 dark:hover:bg-emerald-950"
        }`}
        style={{ borderColor: expanded ? undefined : (color as string) }}
        title={expanded ? "Collapse children" : "Expand children"}
      >
        {childrenLoading ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : expanded ? (
          <Minus className="h-3 w-3" />
        ) : (
          <Plus className="h-3 w-3" />
        )}
      </button>

      <Handle type="source" position={Position.Bottom} className="!bg-muted-foreground" />
    </div>
  );
}

export const GraphNodeType = memo(GraphNodeComponent);
