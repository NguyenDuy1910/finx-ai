"use client";

import { useState, useCallback, useMemo, useRef } from "react";
import type { Node, Edge } from "@xyflow/react";
import dagre from "dagre";
import type {
  GraphNode,
  GraphEdge,
  GraphOverviewResponse,
  NodeLabel,
} from "@/types/graph-explorer.types";
import { NODE_COLORS } from "@/types/graph-explorer.types";
import {
  fetchGraphOverview,
  fetchExploreNode,
  searchGraph,
  semanticSearchGraph,
  fetchLineage,
  fetchNodes,
} from "@/services/graph-explorer.service";

const NODE_MIN_WIDTH = 160;
const NODE_MAX_WIDTH = 320;
const NODE_BASE_HEIGHT = 52; // label row (18) + name row (20) + padding (14)
const NODE_SUMMARY_LINE_HEIGHT = 14; // ~11px font + leading

/**
 * Estimate the rendered size of a node based on its text content.
 * Keeps dagre spacing proportional to actual visual size.
 */
function estimateNodeSize(data: Record<string, unknown>): { w: number; h: number } {
  const label = (data.label as string) || "";
  const summary = (data.summary as string) || "";
  const longest = Math.max(label.length, summary.length);
  // ~7px per char + 48px padding (px-3 both sides + expand btn space)
  const w = Math.max(NODE_MIN_WIDTH, Math.min(NODE_MAX_WIDTH, Math.ceil(longest * 7) + 48));

  let h = NODE_BASE_HEIGHT;
  if (summary) {
    // Estimate wrapped lines: chars per line ≈ (width - 48) / 6.5
    const charsPerLine = Math.max(1, Math.floor((w - 48) / 6.5));
    const lines = Math.min(2, Math.ceil(summary.length / charsPerLine)); // line-clamp-2
    h += lines * NODE_SUMMARY_LINE_HEIGHT;
  }
  return { w, h };
}

function toFlowNode(gn: GraphNode): Node {
  return {
    id: gn.uuid,
    type: "graphNode",
    position: { x: 0, y: 0 },
    data: {
      label: gn.name,
      nodeLabel: gn.label,
      summary: gn.summary,
      attributes: gn.attributes,
      color: NODE_COLORS[gn.label] || "#6B7280",
    },
  };
}

function toFlowEdge(ge: GraphEdge): Edge {
  return {
    id: ge.uuid,
    source: ge.source_node.uuid,
    target: ge.target_node.uuid,
    type: "graphEdge",
    label: ge.edge_type,
    data: {
      edgeType: ge.edge_type,
      fact: ge.fact,
      attributes: ge.attributes,
    },
  };
}

function applyLayout(nodes: Node[], edges: Edge[], direction: string = "TB"): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 80 });

  // Build a size map so each node gets a layout rectangle matching its visual size
  const sizeMap = new Map<string, { w: number; h: number }>();
  for (const node of nodes) {
    const size = estimateNodeSize(node.data as Record<string, unknown>);
    sizeMap.set(node.id, size);
    g.setNode(node.id, { width: size.w, height: size.h });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    const size = sizeMap.get(node.id) || { w: NODE_MIN_WIDTH, h: NODE_BASE_HEIGHT };
    return {
      ...node,
      position: {
        x: pos.x - size.w / 2,
        y: pos.y - size.h / 2,
      },
    };
  });
}

export function useGraphData() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [overview, setOverview] = useState<GraphOverviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [loadingNodes, setLoadingNodes] = useState<Set<string>>(new Set());
  // Track parent→children mapping for collapse (ALL neighbors from explore)
  const [childrenMap, setChildrenMap] = useState<Record<string, string[]>>({});
  // Track edges added by each explore — these get removed/hidden on collapse
  const [exploreEdgesMap, setExploreEdgesMap] = useState<Record<string, string[]>>({});
  // Cache hidden nodes & edges so collapse doesn't destroy data
  const [hiddenNodes, setHiddenNodes] = useState<Record<string, Node[]>>({});
  const [hiddenEdges, setHiddenEdges] = useState<Record<string, Edge[]>>({});

  // Refs to avoid stale closures — always point to latest state
  const expandedNodesRef = useRef(expandedNodes);
  expandedNodesRef.current = expandedNodes;
  const childrenMapRef = useRef(childrenMap);
  childrenMapRef.current = childrenMap;
  const exploreEdgesMapRef = useRef(exploreEdgesMap);
  exploreEdgesMapRef.current = exploreEdgesMap;
  const hiddenNodesRef = useRef(hiddenNodes);
  hiddenNodesRef.current = hiddenNodes;
  const hiddenEdgesRef = useRef(hiddenEdges);
  hiddenEdgesRef.current = hiddenEdges;

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchGraphOverview();
      setOverview(data);
      // Don't populate canvas — let user select an entity type first
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load overview");
    } finally {
      setLoading(false);
    }
  }, []);

  const exploreNode = useCallback(
    async (uuid: string) => {
      // If already expanded, skip — read from ref to avoid stale closure
      if (expandedNodesRef.current.has(uuid)) return;

      // Check if we have cached hidden children — restore them instead of re-fetching
      const cachedNodes = hiddenNodesRef.current[uuid];
      const cachedEdges = hiddenEdgesRef.current[uuid];
      if (cachedNodes && cachedNodes.length > 0) {
        setEdges((prevEdges) => {
          const combined = [...prevEdges, ...(cachedEdges || [])];
          const uniqueEdges = combined.filter(
            (e, i, arr) => arr.findIndex((x) => x.id === e.id) === i
          );

          setNodes((prevNodes) => {
            const existingIds = new Set(prevNodes.map((n) => n.id));
            const updated = prevNodes.map((n) =>
              n.id === uuid ? { ...n, data: { ...n.data, expanded: true } } : n
            );
            // Only add nodes that don't already exist
            const newNodes = cachedNodes.filter((n) => !existingIds.has(n.id));
            const all = [...updated, ...newNodes];

            const nodeIdSet = new Set(all.map((n) => n.id));
            const layoutEdges = uniqueEdges.filter(
              (e) => nodeIdSet.has(e.source) && nodeIdSet.has(e.target)
            );

            return applyLayout(all, layoutEdges);
          });

          return uniqueEdges;
        });

        setExpandedNodes((prev) => new Set([...prev, uuid]));

        // Clear the cache for this node
        setHiddenNodes((prev) => {
          const next = { ...prev };
          delete next[uuid];
          return next;
        });
        setHiddenEdges((prev) => {
          const next = { ...prev };
          delete next[uuid];
          return next;
        });
        return;
      }

      setLoadingNodes((prev) => new Set([...prev, uuid]));
      setError(null);
      try {
        const data = await fetchExploreNode(uuid);
        const centerNode = toFlowNode(data.center);
        const neighborNodes = data.neighbors.map(toFlowNode);
        const apiEdges = data.edges.map(toFlowEdge);

        const neighborIds = neighborNodes.map((n) => n.id);
        const allNodeIds = new Set([centerNode.id, ...neighborIds]);

        // Build a set of node pairs already connected by API edges
        const connectedPairs = new Set<string>();
        for (const edge of apiEdges) {
          connectedPairs.add(`${edge.source}->${edge.target}`);
          connectedPairs.add(`${edge.target}->${edge.source}`);
        }

        // For any neighbor not already connected to the center via an API edge,
        // create a synthetic "explore" edge so the user can see the relationship line
        const syntheticEdges: Edge[] = [];
        for (const neighbor of neighborNodes) {
          const fwd = `${uuid}->${neighbor.id}`;
          const rev = `${neighbor.id}->${uuid}`;
          if (!connectedPairs.has(fwd) && !connectedPairs.has(rev)) {
            syntheticEdges.push({
              id: `explore-${uuid}-${neighbor.id}`,
              source: uuid,
              target: neighbor.id,
              type: "graphEdge",
              label: "RELATED",
              data: {
                edgeType: "RELATED",
                fact: "",
                attributes: {},
                isExploreEdge: true,
              },
            });
          }
        }

        const newFlowEdges = [...apiEdges, ...syntheticEdges];

        // Mark center node as expanded
        centerNode.data = { ...centerNode.data, expanded: true };

        // Update edges first using functional updater so we have the latest state
        // Then update nodes using the merged edges for layout
        setEdges((prevEdges) => {
          const combined = [...prevEdges, ...newFlowEdges];
          const uniqueEdges = combined.filter(
            (e, i, arr) => arr.findIndex((x) => x.id === e.id) === i
          );

          // Now update nodes using these merged edges for correct layout
          setNodes((prevNodes) => {
            const existingIds = new Set(prevNodes.map((n) => n.id));
            const existing = prevNodes.filter((n) => !allNodeIds.has(n.id));
            const updated = existing.map((n) =>
              n.id === uuid ? { ...n, data: { ...n.data, expanded: true } } : n
            );
            const hasCenterAlready = existingIds.has(uuid);
            const combined = [
              ...updated,
              ...(hasCenterAlready ? [] : [centerNode]),
              ...neighborNodes,
            ];
            // Deduplicate nodes
            const seen = new Set<string>();
            const deduped = combined.filter((n) => {
              if (seen.has(n.id)) return false;
              seen.add(n.id);
              return true;
            });

            // Only use edges where both source and target exist in the node set
            const nodeIdSet = new Set(deduped.map((n) => n.id));
            const layoutEdges = uniqueEdges.filter(
              (e) => nodeIdSet.has(e.source) && nodeIdSet.has(e.target)
            );

            // Track ALL neighbors as children of this node for collapse purposes.
            setChildrenMap((prev) => ({ ...prev, [uuid]: neighborIds }));

            // Track which edges were added by this explore
            const newEdgeIds = newFlowEdges.map((e) => e.id);
            setExploreEdgesMap((prev) => ({ ...prev, [uuid]: newEdgeIds }));

            return applyLayout(deduped, layoutEdges);
          });

          return uniqueEdges;
        });

        setExpandedNodes((prev) => new Set([...prev, uuid]));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to explore node");
      } finally {
        setLoadingNodes((prev) => {
          const s = new Set(prev);
          s.delete(uuid);
          return s;
        });
      }
    },
    [] // stable — reads from refs to avoid stale closures
  );

  const collapseNode = useCallback(
    (uuid: string) => {
      const currentChildrenMap = childrenMapRef.current;
      const currentExploreEdges = exploreEdgesMapRef.current;

      // Collect all edge IDs that were added by exploring this node and its descendants
      const edgeIdsToRemove = new Set<string>(currentExploreEdges[uuid] || []);

      // BFS to find descendant nodes to potentially hide
      const descendants = new Set<string>();
      const queue = [...(currentChildrenMap[uuid] || [])];
      while (queue.length > 0) {
        const current = queue.pop()!;
        if (current === uuid || descendants.has(current)) continue;
        descendants.add(current);
        // Also collect edges from expanded descendants
        const descEdges = currentExploreEdges[current];
        if (descEdges) {
          for (const edgeId of descEdges) {
            edgeIdsToRemove.add(edgeId);
          }
        }
        const grandchildren = currentChildrenMap[current];
        if (grandchildren) {
          for (const child of grandchildren) {
            if (!descendants.has(child) && child !== uuid) {
              queue.push(child);
            }
          }
        }
      }

      // Remove explore edges and hide orphaned nodes
      setEdges((prevEdges) => {
        const cachedEdges = prevEdges.filter((e) => edgeIdsToRemove.has(e.id));
        const remainingEdges = prevEdges.filter((e) => !edgeIdsToRemove.has(e.id));

        // Find which descendant nodes are now orphaned (no remaining edges connect them)
        const connectedNodeIds = new Set<string>();
        for (const e of remainingEdges) {
          connectedNodeIds.add(e.source);
          connectedNodeIds.add(e.target);
        }

        setNodes((prevNodes) => {
          const toHideNodes: Node[] = [];
          const remaining: Node[] = [];

          for (const n of prevNodes) {
            if (n.id === uuid) {
              // Keep the collapsed node, update its expanded state
              remaining.push({ ...n, data: { ...n.data, expanded: false } });
            } else if (descendants.has(n.id) && !connectedNodeIds.has(n.id)) {
              // Descendant with no remaining edges — hide it
              toHideNodes.push(n);
            } else {
              remaining.push(n);
            }
          }

          if (toHideNodes.length > 0) {
            setHiddenNodes((prev) => ({ ...prev, [uuid]: toHideNodes }));
          }

          return applyLayout(remaining, remainingEdges);
        });

        if (cachedEdges.length > 0) {
          setHiddenEdges((prev) => ({ ...prev, [uuid]: cachedEdges }));
        }

        return remainingEdges;
      });

      // Mark this node and all descendants as not expanded
      setExpandedNodes((prev) => {
        const next = new Set(prev);
        next.delete(uuid);
        for (const id of descendants) {
          next.delete(id);
        }
        return next;
      });
    },
    [] // stable — reads from refs to avoid stale closures
  );

  const loadLineage = useCallback(async (uuid: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLineage(uuid);
      const flowNodes = data.nodes.map(toFlowNode);
      const flowEdges = data.edges.map(toFlowEdge);
      const laid = applyLayout(flowNodes, flowEdges, "TB");
      setNodes(laid);
      setEdges(flowEdges);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load lineage");
    } finally {
      setLoading(false);
    }
  }, []);

  const searchNodes = useCallback(async (query: string, label?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await searchGraph(query, label, 30);
      const flowNodes = data.nodes.map(toFlowNode);
      const laid = applyLayout(flowNodes, [], "LR");
      setNodes(laid);
      setEdges([]);
      setExpandedNodes(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const semanticSearch = useCallback(async (query: string, label?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await semanticSearchGraph(query, label, 30);
      const flowNodes = data.nodes.map(toFlowNode);
      const laid = applyLayout(flowNodes, [], "LR");
      setNodes(laid);
      setEdges([]);
      setExpandedNodes(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Semantic search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadEntityNodes = useCallback(async (label: NodeLabel) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchNodes(label, { limit: 100 });
      const flowNodes = data.nodes.map(toFlowNode);
      const laid = applyLayout(flowNodes, [], "LR");
      setNodes(laid);
      setEdges([]);
      setExpandedNodes(new Set());
      setChildrenMap({});
      setExploreEdgesMap({});
      setHiddenNodes({});
      setHiddenEdges({});
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to load ${label} nodes`);
    } finally {
      setLoading(false);
    }
  }, []);

  const clearGraph = useCallback(() => {
    setNodes([]);
    setEdges([]);
    setExpandedNodes(new Set());
    setChildrenMap({});
    setExploreEdgesMap({});
    setHiddenNodes({});
    setHiddenEdges({});
    setError(null);
  }, []);

  /**
   * Completely remove a previously-explored node and all nodes/edges
   * that were exclusively introduced by exploring it.
   * Unlike `collapseNode`, this removes the center node itself too.
   */
  const removeNode = useCallback(
    (uuid: string) => {
      const currentChildrenMap = childrenMapRef.current;
      const currentExploreEdges = exploreEdgesMapRef.current;

      // Collect edges to remove
      const edgeIdsToRemove = new Set<string>(currentExploreEdges[uuid] || []);

      // BFS descendants
      const descendants = new Set<string>();
      const queue = [...(currentChildrenMap[uuid] || [])];
      while (queue.length > 0) {
        const current = queue.pop()!;
        if (current === uuid || descendants.has(current)) continue;
        descendants.add(current);
        const descEdges = currentExploreEdges[current];
        if (descEdges) {
          for (const edgeId of descEdges) edgeIdsToRemove.add(edgeId);
        }
        const grandchildren = currentChildrenMap[current];
        if (grandchildren) {
          for (const child of grandchildren) {
            if (!descendants.has(child) && child !== uuid) queue.push(child);
          }
        }
      }

      // Also remove any edge that touches the center node
      setEdges((prevEdges) => {
        const remaining = prevEdges.filter(
          (e) =>
            !edgeIdsToRemove.has(e.id) &&
            e.source !== uuid &&
            e.target !== uuid
        );

        // Find which nodes are still connected after removing those edges
        const connectedNodeIds = new Set<string>();
        for (const e of remaining) {
          connectedNodeIds.add(e.source);
          connectedNodeIds.add(e.target);
        }

        setNodes((prevNodes) => {
          const remaining2 = prevNodes.filter((n) => {
            // Remove the center node itself
            if (n.id === uuid) return false;
            // Remove descendants that are orphaned
            if (descendants.has(n.id) && !connectedNodeIds.has(n.id)) return false;
            return true;
          });
          return remaining2.length > 0
            ? applyLayout(remaining2, remaining)
            : [];
        });

        return remaining;
      });

      // Clean up tracking maps
      setExpandedNodes((prev) => {
        const next = new Set(prev);
        next.delete(uuid);
        for (const id of descendants) next.delete(id);
        return next;
      });
      setChildrenMap((prev) => {
        const next = { ...prev };
        delete next[uuid];
        for (const id of descendants) delete next[id];
        return next;
      });
      setExploreEdgesMap((prev) => {
        const next = { ...prev };
        delete next[uuid];
        for (const id of descendants) delete next[id];
        return next;
      });
      setHiddenNodes((prev) => {
        const next = { ...prev };
        delete next[uuid];
        return next;
      });
      setHiddenEdges((prev) => {
        const next = { ...prev };
        delete next[uuid];
        return next;
      });
    },
    [] // stable — reads from refs
  );

  return useMemo(
    () => ({
      nodes,
      edges,
      overview,
      loading,
      error,
      expandedNodes,
      loadingNodes,
      setNodes,
      setEdges,
      loadOverview,
      exploreNode,
      collapseNode,
      removeNode,
      loadLineage,
      searchNodes,
      semanticSearch,
      loadEntityNodes,
      clearGraph,
    }),
    [
      nodes,
      edges,
      overview,
      loading,
      error,
      expandedNodes,
      loadingNodes,
      setNodes,
      setEdges,
      loadOverview,
      exploreNode,
      collapseNode,
      removeNode,
      loadLineage,
      searchNodes,
      semanticSearch,
      loadEntityNodes,
      clearGraph,
    ]
  );
}
