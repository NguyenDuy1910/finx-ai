"use client";

import { useState, useCallback } from "react";
import { Search, Plus, GitBranch, RotateCcw, Maximize2, Minimize2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NODE_LABELS, NODE_COLORS } from "@/types/graph-explorer.types";
import type { NodeLabel } from "@/types/graph-explorer.types";

interface GraphToolbarProps {
  onSearch: (query: string, label?: string) => void;
  onSemanticSearch: (query: string, label?: string) => void;
  onEntitySelect: (label: NodeLabel) => void;
  onCreateNode: () => void;
  onCreateEdge: () => void;
  onShowLineage: () => void;
  onReset: () => void;
  hasSelectedNode: boolean;
  selectedEntityType: NodeLabel | null;
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
}

export function GraphToolbar({
  onSearch,
  onSemanticSearch,
  onEntitySelect,
  onCreateNode,
  onCreateEdge,
  onShowLineage,
  onReset,
  hasSelectedNode,
  selectedEntityType,
  isFullscreen,
  onToggleFullscreen,
}: GraphToolbarProps) {
  const [query, setQuery] = useState("");
  const [isSemanticMode, setIsSemanticMode] = useState(false);

  const handleSearch = useCallback(() => {
    if (!query.trim()) return;
    if (isSemanticMode) {
      onSemanticSearch(query.trim(), selectedEntityType || undefined);
    } else {
      onSearch(query.trim(), selectedEntityType || undefined);
    }
  }, [query, isSemanticMode, selectedEntityType, onSearch, onSemanticSearch]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") handleSearch();
    },
    [handleSearch]
  );

  return (
    <div className="flex flex-col border-b border-border bg-background">
      {/* Top row: Entity type pills */}
      <div className="flex items-center gap-1.5 px-3 pt-2 pb-1.5 overflow-x-auto">
        <span className="text-xs font-medium text-muted-foreground whitespace-nowrap mr-1">
          Entity:
        </span>
        {NODE_LABELS.map((label) => {
          const isActive = selectedEntityType === label;
          return (
            <button
              key={label}
              onClick={() => onEntitySelect(label)}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all whitespace-nowrap border ${
                isActive
                  ? "text-white shadow-sm scale-105"
                  : "bg-background text-foreground border-border hover:bg-muted"
              }`}
              style={
                isActive
                  ? { backgroundColor: NODE_COLORS[label], borderColor: NODE_COLORS[label] }
                  : undefined
              }
            >
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: NODE_COLORS[label] }}
              />
              {label}
            </button>
          );
        })}
      </div>

      {/* Bottom row: Search + actions */}
      <div className="flex items-center gap-2 px-3 py-2">
        <div className="flex flex-1 items-center gap-2">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isSemanticMode ? "Describe what you're looking for..." : "Search nodes..."}
              className="pl-9 h-9"
            />
          </div>
          <Button
            variant={isSemanticMode ? "default" : "outline"}
            size="sm"
            onClick={() => setIsSemanticMode((prev) => !prev)}
            title={isSemanticMode ? "Switch to keyword search" : "Switch to semantic search"}
            className="gap-1"
          >
            <Sparkles className="h-3.5 w-3.5" />
            AI
          </Button>
          <Button variant="outline" size="sm" onClick={handleSearch}>
            Search
          </Button>
        </div>
        <div className="flex items-center gap-1.5">
          <Button variant="outline" size="sm" onClick={onCreateNode}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Node
          </Button>
          <Button variant="outline" size="sm" onClick={onCreateEdge}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Edge
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onShowLineage}
            disabled={!hasSelectedNode}
          >
            <GitBranch className="mr-1 h-3.5 w-3.5" />
            Lineage
          </Button>
          <Button variant="ghost" size="icon" onClick={onReset} title="Reset">
            <RotateCcw className="h-4 w-4" />
          </Button>
          {onToggleFullscreen && (
            <Button variant="ghost" size="icon" onClick={onToggleFullscreen} title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}>
              {isFullscreen ? (
                <Minimize2 className="h-4 w-4" />
              ) : (
                <Maximize2 className="h-4 w-4" />
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
