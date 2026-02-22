"use client";

import { useEffect, useState, useCallback } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { useGraphData } from "@/hooks/use-graph-data";
import { useGraphCrud } from "@/hooks/use-graph-crud";
import { useGraphSession } from "@/hooks/use-graph-session";
import { GraphToolbar } from "./graph-toolbar";
import { GraphSidebar } from "./graph-sidebar";
import { GraphCanvas } from "./graph-canvas";
import { NodeDetailPanel } from "./node-detail-panel";
import { EdgeDetailPanel } from "./edge-detail-panel";
import { NodeCreateDialog } from "./node-create-dialog";
import { EdgeCreateDialog } from "./edge-create-dialog";
import type { NodeLabel } from "@/types/graph-explorer.types";

interface SelectedNode {
  uuid: string;
  label: string;
  name: string;
  summary: string;
  attributes: Record<string, unknown>;
}

interface SelectedEdge {
  uuid: string;
  edge_type: string;
  fact: string;
  attributes: Record<string, unknown>;
  source_name: string;
  target_name: string;
}

export function GraphExplorerContainer() {
  const graphData = useGraphData();
  const {
    loadOverview,
    exploreNode,
    collapseNode,
    removeNode,
    searchNodes,
    semanticSearch,
    loadEntityNodes,
    loadLineage,
    clearGraph,
    nodes,
    edges,
    overview,
    loading,
    error,
    expandedNodes,
    loadingNodes,
  } = graphData;
  const crud = useGraphCrud();

  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<SelectedEdge | null>(null);
  const [showNodeCreate, setShowNodeCreate] = useState(false);
  const [showEdgeCreate, setShowEdgeCreate] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedEntityType, setSelectedEntityType] = useState<NodeLabel | null>(null);
  const [pinnedNodes, setPinnedNodes] = useState<Set<string>>(new Set());

  // Persist & restore graph view across page refreshes / tab switches
  const session = useGraphSession({
    searchNodes,
    semanticSearch,
    loadEntityNodes,
    exploreNode,
    loadLineage,
    setSelectedEntityType,
    setPinnedNodes,
  });

  // Load overview for the sidebar (domains list) on mount, but don't populate canvas
  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  // Exit fullscreen on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFullscreen]);

  const handleNodeClick = useCallback(
    (nodeId: string, nodeData: Record<string, unknown>) => {
      setSelectedEdge(null);
      setSelectedNode({
        uuid: nodeId,
        label: (nodeData.nodeLabel as string) || "",
        name: (nodeData.label as string) || "",
        summary: (nodeData.summary as string) || "",
        attributes: (nodeData.attributes as Record<string, unknown>) || {},
      });
    },
    []
  );

  const handleEdgeClick = useCallback(
    (edgeId: string, edgeData: Record<string, unknown>) => {
      setSelectedNode(null);
      setSelectedEdge({
        uuid: edgeId,
        edge_type: (edgeData.edgeType as string) || "",
        fact: (edgeData.fact as string) || "",
        attributes: (edgeData.attributes as Record<string, unknown>) || {},
        source_name: "",
        target_name: "",
      });
    },
    []
  );

  const handleNodeDoubleClick = useCallback(
    (nodeId: string) => {
      exploreNode(nodeId);
    },
    [exploreNode]
  );

  const handleExpandNode = useCallback(
    (nodeId: string) => {
      exploreNode(nodeId);
    },
    [exploreNode]
  );

  const handleCollapseNode = useCallback(
    (nodeId: string) => {
      collapseNode(nodeId);
    },
    [collapseNode]
  );

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((prev) => !prev);
  }, []);

  const handleSidebarNodeSelect = useCallback(
    (uuid: string) => {
      exploreNode(uuid);
      session.recordExplore(uuid, selectedEntityType);
    },
    [exploreNode, session, selectedEntityType]
  );

  /** Pin a sidebar node — explore it on the canvas and persist */
  const handleNodePin = useCallback(
    (uuid: string) => {
      exploreNode(uuid);
      setPinnedNodes((prev) => {
        const next = new Set(prev);
        next.add(uuid);
        session.recordPinnedNodes(next);
        return next;
      });
    },
    [exploreNode, session]
  );

  /** Unpin a sidebar node — remove it from the canvas and persist */
  const handleNodeUnpin = useCallback(
    (uuid: string) => {
      removeNode(uuid);
      setPinnedNodes((prev) => {
        const next = new Set(prev);
        next.delete(uuid);
        session.recordPinnedNodes(next);
        return next;
      });
    },
    [removeNode, session]
  );

  const handleSearch = useCallback(
    (query: string, label?: string) => {
      searchNodes(query, label);
      session.recordSearch(query, label);
    },
    [searchNodes, session]
  );

  const handleSemanticSearch = useCallback(
    (query: string, label?: string) => {
      semanticSearch(query, label);
      session.recordSemanticSearch(query, label);
    },
    [semanticSearch, session]
  );

  const handleEntitySelect = useCallback(
    (label: NodeLabel) => {
      setSelectedEntityType(label);
      loadEntityNodes(label);
      session.recordEntitySelect(label);
    },
    [loadEntityNodes, session]
  );

  const handleShowLineage = useCallback(() => {
    if (selectedNode) {
      loadLineage(selectedNode.uuid);
      session.recordLineage(selectedNode.uuid, selectedEntityType);
    }
  }, [selectedNode, loadLineage, session, selectedEntityType]);

  const handleReset = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
    setSelectedEntityType(null);
    setPinnedNodes(new Set());
    clearGraph();
    loadOverview();
    session.clearSession();
  }, [clearGraph, loadOverview, session]);

  const handleNodeUpdate = useCallback(
    async (
      label: string,
      uuid: string,
      data: { name?: string; description?: string; attributes?: Record<string, unknown> }
    ) => {
      const result = await crud.updateNode(label, uuid, data);
      if (result) {
        loadOverview();
      }
      return result;
    },
    [crud, loadOverview]
  );

  const handleNodeDelete = useCallback(
    async (label: string, uuid: string) => {
      const deleted = await crud.deleteNode(label, uuid);
      if (deleted) {
        setSelectedNode(null);
        loadOverview();
      }
      return deleted;
    },
    [crud, loadOverview]
  );

  const handleEdgeUpdate = useCallback(
    async (uuid: string, data: { fact?: string; attributes?: Record<string, unknown> }) => {
      const result = await crud.updateEdge(uuid, data);
      return result;
    },
    [crud]
  );

  const handleEdgeDelete = useCallback(
    async (uuid: string) => {
      const deleted = await crud.deleteEdge(uuid);
      if (deleted) {
        setSelectedEdge(null);
        loadOverview();
      }
      return deleted;
    },
    [crud, loadOverview]
  );

  const handleCreateNode = useCallback(
    async (
      label: string,
      name: string,
      description: string,
      attributes: Record<string, unknown>
    ) => {
      const result = await crud.createNode(label, name, description, attributes);
      if (result) {
        loadOverview();
      }
      return result;
    },
    [crud, loadOverview]
  );

  const handleCreateEdge = useCallback(
    async (
      sourceUuid: string,
      targetUuid: string,
      edgeType: string,
      fact: string,
      attributes: Record<string, unknown>
    ) => {
      const result = await crud.createEdge(sourceUuid, targetUuid, edgeType, fact, attributes);
      if (result) {
        loadOverview();
      }
      return result;
    },
    [crud, loadOverview]
  );

  return (
    <div
      className={`flex flex-col rounded-lg border border-border overflow-hidden transition-all duration-300 ${
        isFullscreen
          ? "fixed inset-0 z-50 h-screen w-screen rounded-none"
          : "h-[calc(100vh-12rem)]"
      }`}
    >
      <GraphToolbar
        onSearch={handleSearch}
        onSemanticSearch={handleSemanticSearch}
        onEntitySelect={handleEntitySelect}
        onCreateNode={() => setShowNodeCreate(true)}
        onCreateEdge={() => setShowEdgeCreate(true)}
        onShowLineage={handleShowLineage}
        onReset={handleReset}
        hasSelectedNode={selectedNode !== null}
        selectedEntityType={selectedEntityType}
        isFullscreen={isFullscreen}
        onToggleFullscreen={toggleFullscreen}
      />
      <div className="flex flex-1 overflow-hidden">
        <GraphSidebar
          overview={overview}
          onNodePin={handleNodePin}
          onNodeUnpin={handleNodeUnpin}
          pinnedNodes={pinnedNodes}
          loading={loading}
        />
        <ReactFlowProvider>
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeClick}
            onNodeDoubleClick={handleNodeDoubleClick}
            onExpandNode={handleExpandNode}
            onCollapseNode={handleCollapseNode}
            expandedNodes={expandedNodes}
            loadingNodes={loadingNodes}
          />
        </ReactFlowProvider>
        {selectedNode && (
          <NodeDetailPanel
            node={selectedNode}
            onUpdate={handleNodeUpdate}
            onDelete={handleNodeDelete}
            onClose={() => setSelectedNode(null)}
            loading={crud.loading}
          />
        )}
        {selectedEdge && (
          <EdgeDetailPanel
            edge={selectedEdge}
            onUpdate={handleEdgeUpdate}
            onDelete={handleEdgeDelete}
            onClose={() => setSelectedEdge(null)}
            loading={crud.loading}
          />
        )}
      </div>
      {(error || crud.error) && (
        <div className="border-t border-border bg-red-500/10 px-3 py-1.5 text-xs text-red-500">
          {error || crud.error}
        </div>
      )}
      <NodeCreateDialog
        open={showNodeCreate}
        onClose={() => setShowNodeCreate(false)}
        onCreate={handleCreateNode}
        loading={crud.loading}
      />
      <EdgeCreateDialog
        open={showEdgeCreate}
        onClose={() => setShowEdgeCreate(false)}
        onCreate={handleCreateEdge}
        loading={crud.loading}
      />
    </div>
  );
}
