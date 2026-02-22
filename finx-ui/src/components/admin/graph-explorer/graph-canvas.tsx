"use client";

import { useCallback, useEffect, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { GraphNodeType } from "./custom-nodes";
import { GraphEdgeType } from "./custom-edges";
import { GraphContextProvider } from "./graph-context";

interface GraphCanvasProps {
  nodes: Node[];
  edges: Edge[];
  onNodeClick: (nodeId: string, nodeData: Record<string, unknown>) => void;
  onEdgeClick: (edgeId: string, edgeData: Record<string, unknown>) => void;
  onNodeDoubleClick: (nodeId: string) => void;
  onExpandNode: (nodeId: string) => void;
  onCollapseNode: (nodeId: string) => void;
  expandedNodes: Set<string>;
  loadingNodes: Set<string>;
}

const nodeTypes = { graphNode: GraphNodeType };
const edgeTypes = { graphEdge: GraphEdgeType };

export function GraphCanvas({
  nodes: inputNodes,
  edges: inputEdges,
  onNodeClick,
  onEdgeClick,
  onNodeDoubleClick,
  onExpandNode,
  onCollapseNode,
  expandedNodes,
  loadingNodes,
}: GraphCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(inputNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(inputEdges);

  useEffect(() => {
    setNodes(inputNodes);
  }, [inputNodes, setNodes]);

  useEffect(() => {
    setEdges(inputEdges);
  }, [inputEdges, setEdges]);

  // Context value — provides expand/collapse state & callbacks to node components
  const graphContextValue = useMemo(
    () => ({
      expandedNodes,
      loadingNodes,
      onExpandNode,
      onCollapseNode,
    }),
    [expandedNodes, loadingNodes, onExpandNode, onCollapseNode]
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeClick(node.id, node.data as Record<string, unknown>);
    },
    [onNodeClick]
  );

  const handleEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      onEdgeClick(edge.id, (edge.data || {}) as Record<string, unknown>);
    },
    [onEdgeClick]
  );

  const handleNodeDoubleClick: NodeMouseHandler<Node> = useCallback(
    (_, node) => {
      onNodeDoubleClick(node.id);
    },
    [onNodeDoubleClick]
  );

  return (
    <div className="flex-1">
      <GraphContextProvider value={graphContextValue}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          onEdgeClick={handleEdgeClick}
          onNodeDoubleClick={handleNodeDoubleClick}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          minZoom={0.1}
          maxZoom={2}
          defaultEdgeOptions={{ animated: false }}
        >
          {/* Arrow marker for directed edges */}
          <svg>
            <defs>
              <marker
                id="arrowhead"
                viewBox="0 0 10 10"
                refX={8}
                refY={5}
                markerWidth={6}
                markerHeight={6}
                orient="auto-start-reverse"
              >
                <path
                  d="M 0 0 L 10 5 L 0 10 z"
                  fill="#64748B"
                />
              </marker>
            </defs>
          </svg>
          <Background gap={20} size={1} />
          <Controls />
          <MiniMap
            nodeColor={(node) => {
              const data = node.data as Record<string, unknown>;
              return (data.color as string) || "#6B7280";
            }}
            className="!bg-background !border-border"
          />
        </ReactFlow>
      </GraphContextProvider>
    </div>
  );
}
