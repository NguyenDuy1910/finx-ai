"use client";

import { useMemo, useCallback, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { Maximize2, Minimize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  KGNode,
  KGEdge,
  TablePreviewResult,
} from "@/types/schema-pipeline.types";

interface IndexingGraphFlowProps {
  previews: Record<string, TablePreviewResult>;
  indexedTableNames: string[];
}

const TYPE_COLORS: Record<string, string> = {
  table: "#3B82F6",
  column: "#8B5CF6",
  domain: "#10B981",
  entity: "#F59E0B",
  concept: "#EC4899",
  product_area: "#06B6D4",
  example_query: "#EAB308",
  jargon: "#F97316",
};

const EDGE_TYPE_COLORS: Record<string, string> = {
  structural: "#64748B",
  semantic: "#6366F1",
  business: "#0EA5E9",
};

function getNodeColor(type: string): string {
  return TYPE_COLORS[type] || "#6B7280";
}

function getEdgeColor(type: string): string {
  return EDGE_TYPE_COLORS[type] || "#64748B";
}

function aggregateGraphData(
  previews: Record<string, TablePreviewResult>,
  indexedTableNames: string[]
): { nodes: KGNode[]; edges: KGEdge[] } {
  const nodeMap = new Map<string, KGNode>();
  const edgeSet: KGEdge[] = [];
  const edgeKeys = new Set<string>();

  for (const tableName of indexedTableNames) {
    const preview = previews[tableName];
    if (!preview || preview.status !== "done") continue;

    for (const node of preview.kg_nodes ?? []) {
      if (!nodeMap.has(node.id)) {
        nodeMap.set(node.id, node);
      }
    }

    for (const edge of preview.kg_edges ?? []) {
      const key = `${edge.source}→${edge.target}→${edge.label}`;
      if (!edgeKeys.has(key)) {
        edgeKeys.add(key);
        edgeSet.push(edge);
      }
    }
  }

  return { nodes: Array.from(nodeMap.values()), edges: edgeSet };
}

function buildFlowNodes(kgNodes: KGNode[]): Node[] {
  return kgNodes.map((n) => ({
    id: n.id,
    type: "default",
    position: { x: 0, y: 0 },
    data: {
      label: n.label,
      nodeType: n.type,
      description: n.description,
    },
    style: {
      background: getNodeColor(n.type),
      color: "#ffffff",
      border: "none",
      borderRadius: "8px",
      padding: "8px 12px",
      fontSize: "12px",
      fontWeight: 600,
      minWidth: "120px",
      textAlign: "center" as const,
      boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
    },
  }));
}

function buildFlowEdges(kgEdges: KGEdge[]): Edge[] {
  return kgEdges.map((e, i) => ({
    id: `edge-${i}-${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    label: e.label,
    animated: false,
    style: {
      stroke: getEdgeColor(e.type),
      strokeWidth: 1.5,
    },
    labelStyle: {
      fontSize: 10,
      fill: getEdgeColor(e.type),
      fontWeight: 500,
    },
    labelBgStyle: {
      fill: "#1e293b",
      fillOpacity: 0.85,
    },
    markerEnd: {
      type: "arrowclosed" as const,
      color: getEdgeColor(e.type),
    },
  }));
}

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 80, ranksep: 100 });

  for (const node of nodes) {
    g.setNode(node.id, { width: 160, height: 50 });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      position: { x: pos.x - 80, y: pos.y - 25 },
    };
  });
}

function GraphFlowInner({ previews, indexedTableNames }: IndexingGraphFlowProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const { kgNodes, kgEdges, flowNodes, flowEdges } = useMemo(() => {
    const { nodes: kgN, edges: kgE } = aggregateGraphData(previews, indexedTableNames);
    const fNodes = buildFlowNodes(kgN);
    const fEdges = buildFlowEdges(kgE);
    const laidOut = applyDagreLayout(fNodes, fEdges);
    return { kgNodes: kgN, kgEdges: kgE, flowNodes: laidOut, flowEdges: fEdges };
  }, [previews, indexedTableNames]);

  const [nodes, , onNodesChange] = useNodesState(flowNodes);
  const [edges, , onEdgesChange] = useEdgesState(flowEdges);

  const uniqueTypes = useMemo(() => {
    const types = new Set<string>();
    for (const n of kgNodes) {
      types.add(n.type);
    }
    return Array.from(types);
  }, [kgNodes]);

  const toggleExpand = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  if (kgNodes.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-border/40 bg-muted/20 p-8 text-sm text-muted-foreground">
        No graph data available. Preview tables before indexing to see the knowledge graph flow.
      </div>
    );
  }

  const containerHeight = isExpanded ? "calc(100vh - 200px)" : "480px";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <p className="text-sm font-medium">
            {kgNodes.length} nodes, {kgEdges.length} edges
          </p>
          <div className="flex flex-wrap gap-2">
            {uniqueTypes.map((type) => (
              <div key={type} className="flex items-center gap-1">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: getNodeColor(type) }}
                />
                <span className="text-[10px] text-muted-foreground capitalize">
                  {type.replace(/_/g, " ")}
                </span>
              </div>
            ))}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={toggleExpand} className="gap-1.5">
          {isExpanded ? (
            <Minimize2 className="h-4 w-4" />
          ) : (
            <Maximize2 className="h-4 w-4" />
          )}
          {isExpanded ? "Collapse" : "Expand"}
        </Button>
      </div>

      <div
        className="overflow-hidden rounded-xl border border-border/40 bg-[#0d1117]"
        style={{ height: containerHeight, transition: "height 0.3s ease" }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          minZoom={0.1}
          maxZoom={2}
          defaultEdgeOptions={{ animated: false }}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} size={1} color="#1e293b" />
          <Controls className="!bg-slate-800 !border-slate-600 [&>button]:!bg-slate-700 [&>button]:!border-slate-600 [&>button]:!text-slate-300" />
          <MiniMap
            nodeColor={(node) => {
              const data = node.data as Record<string, unknown>;
              const nodeType = (data.nodeType as string) || "";
              return getNodeColor(nodeType);
            }}
            className="!bg-slate-900 !border-slate-700"
          />
        </ReactFlow>
      </div>
    </div>
  );
}

export function IndexingGraphFlow(props: IndexingGraphFlowProps) {
  return (
    <ReactFlowProvider>
      <GraphFlowInner {...props} />
    </ReactFlowProvider>
  );
}
