import { ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { SearchResultItem } from "@/types/search.types";

interface SearchResultCardProps {
  item: SearchResultItem;
  icon: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
}

export function SearchResultCard({
  item,
  icon,
  onClick,
  active,
}: SearchResultCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors",
        onClick && "cursor-pointer hover:bg-accent",
        active
          ? "border-primary/30 bg-primary/5"
          : "border-border bg-card"
      )}
    >
      <div className="mt-0.5 shrink-0 text-primary">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{item.name}</span>
          {item.label && (
            <Badge variant="default" className="shrink-0 text-[10px]">
              {item.label}
            </Badge>
          )}
          <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
            {(item.score * 100).toFixed(0)}%
          </span>
        </div>
        {item.summary && (
          <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
            {item.summary}
          </p>
        )}
      </div>
      {onClick && (
        <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      )}
    </button>
  );
}
