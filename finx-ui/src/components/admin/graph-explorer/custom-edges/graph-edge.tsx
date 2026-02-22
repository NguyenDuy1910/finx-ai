"use client";

import { memo } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";

interface GraphEdgeData {
  edgeType?: string;
  fact?: string;
  attributes?: Record<string, unknown>;
  isExploreEdge?: boolean;
  [key: string]: unknown;
}

function GraphEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  label,
  selected,
  data,
}: EdgeProps) {
  const edgeData = (data || {}) as GraphEdgeData;
  const isExploreEdge = edgeData.isExploreEdge === true;

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  // Different styles for real relationship edges vs synthetic explore edges
  const strokeColor = selected
    ? "#2563EB"
    : isExploreEdge
      ? "#94A3B8"
      : "#64748B";

  const strokeWidth = selected ? 2.5 : isExploreEdge ? 1.5 : 2;
  const strokeDasharray = isExploreEdge ? "6 3" : undefined;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: strokeColor,
          strokeWidth,
          strokeDasharray,
        }}
        markerEnd={isExploreEdge ? undefined : "url(#arrowhead)"}
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            className={`nodrag nopan pointer-events-auto absolute rounded px-1.5 py-0.5 text-[10px] shadow-sm border transition-colors ${
              selected
                ? "bg-blue-100 text-blue-700 border-blue-300 font-medium dark:bg-blue-950 dark:text-blue-300 dark:border-blue-700"
                : isExploreEdge
                  ? "bg-slate-100 text-slate-500 border-slate-300 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-600"
                  : "bg-white text-slate-700 border-slate-300 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-600"
            }`}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const GraphEdgeType = memo(GraphEdgeComponent);
