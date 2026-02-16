"use client";

import { HTMLAttributes, forwardRef, useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown } from "lucide-react";

interface CollapsibleProps extends HTMLAttributes<HTMLDivElement> {
  title: string;
  defaultOpen?: boolean;
  badge?: string | number;
}

const Collapsible = forwardRef<HTMLDivElement, CollapsibleProps>(
  ({ title, defaultOpen = false, badge, className, children, ...props }, ref) => {
    const [open, setOpen] = useState(defaultOpen);
    return (
      <div
        ref={ref}
        className={cn("rounded-lg border border-border", className)}
        {...props}
      >
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium transition-colors hover:bg-accent"
        >
          <span className="flex items-center gap-2">
            {title}
            {badge !== undefined && (
              <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                {badge}
              </span>
            )}
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-muted-foreground transition-transform",
              open && "rotate-180"
            )}
          />
        </button>
        {open && (
          <div className="border-t border-border px-4 py-3">{children}</div>
        )}
      </div>
    );
  }
);

Collapsible.displayName = "Collapsible";

export { Collapsible };
