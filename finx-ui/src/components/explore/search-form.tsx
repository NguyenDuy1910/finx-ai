"use client";

import { Search, Loader2, ArrowRightLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface SearchFormProps {
  query: string;
  onQueryChange: (value: string) => void;
  onSearch: (e?: React.FormEvent) => void;
  searching: boolean;
  joinSource: string;
  onJoinSourceChange: (value: string) => void;
  joinTarget: string;
  onJoinTargetChange: (value: string) => void;
  onFindJoinPath: () => void;
}

export function SearchForm({
  query,
  onQueryChange,
  onSearch,
  searching,
  joinSource,
  onJoinSourceChange,
  joinTarget,
  onJoinTargetChange,
  onFindJoinPath,
}: SearchFormProps) {
  return (
    <div className="border-b border-border/60 p-4 space-y-3">
      <form onSubmit={onSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/50" />
          <Input
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Search tables, columns, entities..."
            className="pl-9"
          />
        </div>
        <Button type="submit" disabled={searching || !query.trim()} className="gap-1.5">
          {searching ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <>
              <Search className="h-3.5 w-3.5" />
              Search
            </>
          )}
        </Button>
      </form>

      <div className="rounded-lg border border-dashed border-border/60 bg-muted/20 p-3">
        <p className="mb-2 text-[11px] font-medium text-muted-foreground/60 uppercase tracking-wider">
          Find Join Path
        </p>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="mb-1 block text-xs text-muted-foreground">
              Source table
            </label>
            <Input
              value={joinSource}
              onChange={(e) => onJoinSourceChange(e.target.value)}
              placeholder="e.g. branch"
              className="h-8 text-xs"
            />
          </div>
          <ArrowRightLeft className="mb-1.5 h-4 w-4 shrink-0 text-muted-foreground/40" />
          <div className="flex-1">
            <label className="mb-1 block text-xs text-muted-foreground">
              Target table
            </label>
            <Input
              value={joinTarget}
              onChange={(e) => onJoinTargetChange(e.target.value)}
              placeholder="e.g. account"
              className="h-8 text-xs"
            />
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={onFindJoinPath}
            disabled={!joinSource.trim() || !joinTarget.trim()}
            className="h-8"
          >
            Find
          </Button>
        </div>
      </div>
    </div>
  );
}
