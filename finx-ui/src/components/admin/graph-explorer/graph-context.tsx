"use client";

import { createContext, useContext } from "react";

interface GraphContextValue {
  expandedNodes: Set<string>;
  loadingNodes: Set<string>;
  onExpandNode: (nodeId: string) => void;
  onCollapseNode: (nodeId: string) => void;
}

const GraphContext = createContext<GraphContextValue>({
  expandedNodes: new Set(),
  loadingNodes: new Set(),
  onExpandNode: () => {},
  onCollapseNode: () => {},
});

export const GraphContextProvider = GraphContext.Provider;

export function useGraphContext() {
  return useContext(GraphContext);
}
