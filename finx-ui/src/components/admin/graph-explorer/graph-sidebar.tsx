"use client";

import { useState, useCallback } from "react";
import { ChevronRight, ChevronDown, Check } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { NODE_COLORS } from "@/types/graph-explorer.types";
import type { GraphOverviewResponse } from "@/types/graph-explorer.types";
import { fetchNodes } from "@/services/graph-explorer.service";

interface SidebarItem {
  uuid: string;
  name: string;
  label: string;
  children?: SidebarItem[];
  childCount?: number;
}

interface GraphSidebarProps {
  overview: GraphOverviewResponse | null;
  onNodePin: (uuid: string) => void;
  onNodeUnpin: (uuid: string) => void;
  pinnedNodes: Set<string>;
  loading: boolean;
}

export function GraphSidebar({
  overview,
  onNodePin,
  onNodeUnpin,
  pinnedNodes,
  loading,
}: GraphSidebarProps) {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [children, setChildren] = useState<Record<string, SidebarItem[]>>({});
  const [loadingChildren, setLoadingChildren] = useState<Set<string>>(new Set());

  const items: SidebarItem[] = (overview?.domains || []).map((d) => ({
    uuid: d.uuid,
    name: d.name,
    label: "Domain",
    childCount: d.table_count,
  }));

  const toggleExpand = useCallback(
    async (uuid: string) => {
      const next = new Set(expanded);
      if (next.has(uuid)) {
        next.delete(uuid);
        setExpanded(next);
        return;
      }
      next.add(uuid);
      setExpanded(next);

      if (!children[uuid]) {
        setLoadingChildren((prev) => new Set([...prev, uuid]));
        try {
          const result = await fetchNodes("Table", { limit: 200 });
          const tableItems: SidebarItem[] = result.nodes.map((n) => ({
            uuid: n.uuid,
            name: n.name,
            label: "Table",
          }));
          setChildren((prev) => ({ ...prev, [uuid]: tableItems }));
        } catch {
          setChildren((prev) => ({ ...prev, [uuid]: [] }));
        } finally {
          setLoadingChildren((prev) => {
            const s = new Set(prev);
            s.delete(uuid);
            return s;
          });
        }
      }
    },
    [expanded, children]
  );

  const handleTogglePin = useCallback(
    (e: React.MouseEvent, uuid: string) => {
      e.stopPropagation();
      if (pinnedNodes.has(uuid)) {
        onNodeUnpin(uuid);
      } else {
        onNodePin(uuid);
      }
    },
    [pinnedNodes, onNodePin, onNodeUnpin]
  );

  const filtered = search
    ? items.filter((i) => i.name.toLowerCase().includes(search.toLowerCase()))
    : items;

  if (loading && !overview) {
    return (
      <div className="flex w-60 flex-col border-r border-border bg-background">
        <div className="border-b border-border p-2">
          <Skeleton className="h-9 w-full" />
        </div>
        <div className="space-y-2 p-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-60 flex-col border-r border-border bg-background">
      {/* Header with pinned count */}
      <div className="border-b border-border p-2 space-y-1.5">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter domains..."
          className="h-8 text-xs"
        />
        {pinnedNodes.size > 0 && (
          <div className="flex items-center gap-1.5 px-1">
            <div className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
            <span className="text-[10px] text-muted-foreground">
              {pinnedNodes.size} node{pinnedNodes.size !== 1 ? "s" : ""} selected
            </span>
          </div>
        )}
      </div>
      <ScrollArea className="flex-1">
        <div className="p-1">
          {filtered.length === 0 && (
            <div className="px-2 py-4 text-center text-xs text-muted-foreground">
              No domains found
            </div>
          )}
          {filtered.map((item) => {
            const isPinned = pinnedNodes.has(item.uuid);
            return (
              <div key={item.uuid}>
                <div className="flex items-center">
                  {/* Checkbox */}
                  <button
                    onClick={(e) => handleTogglePin(e, item.uuid)}
                    className={`ml-1 mr-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-all ${
                      isPinned
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-muted-foreground/30 hover:border-primary/50"
                    }`}
                    title={isPinned ? "Remove from canvas" : "Add to canvas"}
                    aria-label={isPinned ? `Unpin ${item.name}` : `Pin ${item.name}`}
                  >
                    {isPinned && <Check className="h-3 w-3" />}
                  </button>
                  {/* Expand / row */}
                  <button
                    onClick={() => toggleExpand(item.uuid)}
                    className="flex flex-1 items-center gap-1.5 rounded px-1.5 py-1.5 text-left text-sm hover:bg-accent transition-colors"
                  >
                    {item.childCount !== undefined && item.childCount > 0 ? (
                      expanded.has(item.uuid) ? (
                        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      )
                    ) : (
                      <span className="w-3.5" />
                    )}
                    <div
                      className="h-2 w-2 rounded-full shrink-0"
                      style={{
                        backgroundColor:
                          NODE_COLORS[item.label as keyof typeof NODE_COLORS] || "#6B7280",
                      }}
                    />
                    <span className={`flex-1 truncate ${isPinned ? "font-medium" : ""}`}>
                      {item.name}
                    </span>
                    {item.childCount !== undefined && (
                      <Badge className="ml-auto text-[10px]">{item.childCount}</Badge>
                    )}
                  </button>
                </div>
                {expanded.has(item.uuid) && (
                  <div className="ml-4 border-l border-border pl-2">
                    {loadingChildren.has(item.uuid) ? (
                      <div className="space-y-1 py-1">
                        {Array.from({ length: 3 }).map((_, i) => (
                          <Skeleton key={i} className="h-6 w-full" />
                        ))}
                      </div>
                    ) : (
                      (children[item.uuid] || []).map((child) => {
                        const isChildPinned = pinnedNodes.has(child.uuid);
                        return (
                          <div key={child.uuid} className="flex items-center">
                            <button
                              onClick={(e) => handleTogglePin(e, child.uuid)}
                              className={`ml-1 mr-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border transition-all ${
                                isChildPinned
                                  ? "border-primary bg-primary text-primary-foreground"
                                  : "border-muted-foreground/30 hover:border-primary/50"
                              }`}
                              title={isChildPinned ? "Remove from canvas" : "Add to canvas"}
                            >
                              {isChildPinned && <Check className="h-2.5 w-2.5" />}
                            </button>
                            <button
                              onClick={(e) => handleTogglePin(e, child.uuid)}
                              className="flex flex-1 items-center gap-1.5 rounded px-1.5 py-1 text-left text-xs hover:bg-accent transition-colors"
                            >
                              <div
                                className="h-1.5 w-1.5 rounded-full shrink-0"
                                style={{
                                  backgroundColor:
                                    NODE_COLORS[child.label as keyof typeof NODE_COLORS] || "#6B7280",
                                }}
                              />
                              <span className={`truncate ${isChildPinned ? "font-medium" : ""}`}>
                                {child.name}
                              </span>
                            </button>
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </ScrollArea>
      {overview?.stats && (
        <div className="border-t border-border p-2">
          <div className="grid grid-cols-2 gap-1 text-[10px] text-muted-foreground">
            {Object.entries(overview.stats).map(([key, value]) => (
              <div key={key} className="flex justify-between">
                <span>{key}</span>
                <span className="font-medium">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
