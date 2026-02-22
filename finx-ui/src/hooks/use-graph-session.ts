"use client";

import { useCallback, useEffect, useRef } from "react";
import type { NodeLabel } from "@/types/graph-explorer.types";

// ── Types ────────────────────────────────────────────────────

interface EntityAction {
  type: "entity";
  label: NodeLabel;
}

interface SearchAction {
  type: "search";
  query: string;
  label?: string;
}

interface SemanticSearchAction {
  type: "semantic-search";
  query: string;
  label?: string;
}

interface ExploreAction {
  type: "explore";
  uuid: string;
}

interface LineageAction {
  type: "lineage";
  uuid: string;
}

/** Pinned-nodes mode — user selected specific sidebar nodes */
interface PinnedAction {
  type: "pinned";
  uuids: string[];
}

type GraphAction =
  | EntityAction
  | SearchAction
  | SemanticSearchAction
  | ExploreAction
  | LineageAction
  | PinnedAction;

interface GraphSessionState {
  action: GraphAction | null;
  selectedEntityType: NodeLabel | null;
  /** UUIDs pinned in the sidebar */
  pinnedNodes: string[];
}

// ── Storage key ──────────────────────────────────────────────

const STORAGE_KEY = "finx-graph-session";

function loadSession(): GraphSessionState | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as GraphSessionState) : null;
  } catch {
    return null;
  }
}

function saveSession(state: GraphSessionState): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // storage full — ignore
  }
}

/** Load only the pinned nodes array (for initial state before hook runs) */
export function loadPinnedNodes(): string[] {
  const saved = loadSession();
  return saved?.pinnedNodes ?? [];
}

// ── Hook ─────────────────────────────────────────────────────

interface UseGraphSessionOpts {
  searchNodes: (query: string, label?: string) => void;
  semanticSearch: (query: string, label?: string) => void;
  loadEntityNodes: (label: NodeLabel) => void;
  exploreNode: (uuid: string) => void;
  loadLineage: (uuid: string) => void;
  setSelectedEntityType: (label: NodeLabel | null) => void;
  setPinnedNodes: (nodes: Set<string>) => void;
}

/**
 * Persists the graph explorer's "view intent" to sessionStorage so that
 * a page refresh (or navigating away and back) restores the same view.
 */
export function useGraphSession(opts: UseGraphSessionOpts) {
  const optsRef = useRef(opts);
  optsRef.current = opts;
  const restoredRef = useRef(false);

  // ── Restore on mount ───────────────────────────────────────
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;

    const saved = loadSession();
    if (!saved) return;

    // Restore selected entity type
    if (saved.selectedEntityType) {
      optsRef.current.setSelectedEntityType(saved.selectedEntityType);
    }

    // Restore pinned nodes & replay explores
    if (saved.pinnedNodes && saved.pinnedNodes.length > 0) {
      optsRef.current.setPinnedNodes(new Set(saved.pinnedNodes));
      // Re-explore each pinned node to rebuild the canvas
      for (const uuid of saved.pinnedNodes) {
        optsRef.current.exploreNode(uuid);
      }
      return; // pinned mode takes priority
    }

    if (!saved.action) return;

    // Replay the last action
    const { action } = saved;
    switch (action.type) {
      case "entity":
        optsRef.current.loadEntityNodes(action.label);
        break;
      case "search":
        optsRef.current.searchNodes(action.query, action.label);
        break;
      case "semantic-search":
        optsRef.current.semanticSearch(action.query, action.label);
        break;
      case "explore":
        optsRef.current.exploreNode(action.uuid);
        break;
      case "lineage":
        optsRef.current.loadLineage(action.uuid);
        break;
      case "pinned":
        if (action.uuids.length > 0) {
          optsRef.current.setPinnedNodes(new Set(action.uuids));
          for (const uuid of action.uuids) {
            optsRef.current.exploreNode(uuid);
          }
        }
        break;
    }
  }, []);

  // ── Record helpers ─────────────────────────────────────────

  const persist = useCallback(
    (action: GraphAction, entityType: NodeLabel | null, pinned: string[] = []) => {
      saveSession({
        action,
        selectedEntityType: entityType,
        pinnedNodes: pinned,
      });
    },
    []
  );

  const recordEntitySelect = useCallback(
    (label: NodeLabel) => {
      persist({ type: "entity", label }, label);
    },
    [persist]
  );

  const recordSearch = useCallback(
    (query: string, label?: string) => {
      persist({ type: "search", query, label }, null);
    },
    [persist]
  );

  const recordSemanticSearch = useCallback(
    (query: string, label?: string) => {
      persist({ type: "semantic-search", query, label }, null);
    },
    [persist]
  );

  const recordExplore = useCallback(
    (uuid: string, entityType: NodeLabel | null) => {
      persist({ type: "explore", uuid }, entityType);
    },
    [persist]
  );

  const recordLineage = useCallback(
    (uuid: string, entityType: NodeLabel | null) => {
      persist({ type: "lineage", uuid }, entityType);
    },
    [persist]
  );

  /** Persist the current pinned-nodes set */
  const recordPinnedNodes = useCallback(
    (pinned: Set<string>) => {
      const arr = Array.from(pinned);
      persist({ type: "pinned", uuids: arr }, null, arr);
    },
    [persist]
  );

  const clearSession = useCallback(() => {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  return {
    recordEntitySelect,
    recordSearch,
    recordSemanticSearch,
    recordExplore,
    recordLineage,
    recordPinnedNodes,
    clearSession,
  } as const;
}
