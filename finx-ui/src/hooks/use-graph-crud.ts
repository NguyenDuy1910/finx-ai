"use client";

import { useState, useCallback } from "react";
import type { GraphNode, GraphEdge, NodeLabel } from "@/types/graph-explorer.types";
import {
  createNode,
  updateNode,
  deleteNode,
  createEdge,
  updateEdge,
  deleteEdge,
  fetchNodes,
  fetchEdges,
} from "@/services/graph-explorer.service";

export function useGraphCrud() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreateNode = useCallback(
    async (
      label: string,
      name: string,
      description: string,
      attributes: Record<string, unknown>
    ): Promise<GraphNode | null> => {
      setLoading(true);
      setError(null);
      try {
        const node = await createNode(label, { name, description, attributes });
        return node;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to create node");
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const handleUpdateNode = useCallback(
    async (
      label: string,
      uuid: string,
      data: { name?: string; description?: string; attributes?: Record<string, unknown> }
    ): Promise<GraphNode | null> => {
      setLoading(true);
      setError(null);
      try {
        const node = await updateNode(label, uuid, data);
        return node;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to update node");
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const handleDeleteNode = useCallback(
    async (label: string, uuid: string): Promise<boolean> => {
      setLoading(true);
      setError(null);
      try {
        await deleteNode(label, uuid);
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to delete node");
        return false;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const handleCreateEdge = useCallback(
    async (
      sourceUuid: string,
      targetUuid: string,
      edgeType: string,
      fact: string,
      attributes: Record<string, unknown>
    ): Promise<GraphEdge | null> => {
      setLoading(true);
      setError(null);
      try {
        const edge = await createEdge({
          source_uuid: sourceUuid,
          target_uuid: targetUuid,
          edge_type: edgeType,
          fact,
          attributes,
        });
        return edge;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to create edge");
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const handleUpdateEdge = useCallback(
    async (
      uuid: string,
      data: { fact?: string; attributes?: Record<string, unknown> }
    ): Promise<GraphEdge | null> => {
      setLoading(true);
      setError(null);
      try {
        const edge = await updateEdge(uuid, data);
        return edge;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to update edge");
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const handleDeleteEdge = useCallback(async (uuid: string): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      await deleteEdge(uuid);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete edge");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const loadNodesList = useCallback(
    async (label: NodeLabel, offset = 0, limit = 50, search?: string) => {
      setLoading(true);
      setError(null);
      try {
        return await fetchNodes(label, { offset, limit, search });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load nodes");
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const loadEdgesList = useCallback(
    async (params?: {
      source_uuid?: string;
      target_uuid?: string;
      edge_type?: string;
      offset?: number;
      limit?: number;
    }) => {
      setLoading(true);
      setError(null);
      try {
        return await fetchEdges(params);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load edges");
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return {
    loading,
    error,
    createNode: handleCreateNode,
    updateNode: handleUpdateNode,
    deleteNode: handleDeleteNode,
    createEdge: handleCreateEdge,
    updateEdge: handleUpdateEdge,
    deleteEdge: handleDeleteEdge,
    loadNodesList,
    loadEdgesList,
  };
}
