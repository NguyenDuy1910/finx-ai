"use client";

import { useCallback, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";

interface ResizeHandleProps {
  onResize: (newWidth: number) => void;
  minWidth?: number;
  maxWidth?: number;
  className?: string;
}

/**
 * Draggable vertical resize handle between chat area and side panel.
 * Drag left/right to resize. Double-click to reset to default width.
 */
export function ResizeHandle({
  onResize,
  minWidth = 280,
  maxWidth = 600,
  className,
}: ResizeHandleProps) {
  const isDragging = useRef(false);
  const handleRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      isDragging.current = true;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const handleMouseMove = (e: MouseEvent) => {
        if (!isDragging.current) return;
        // Panel is on the right, so width = viewport width - mouse X
        const newWidth = window.innerWidth - e.clientX;
        const clamped = Math.min(maxWidth, Math.max(minWidth, newWidth));
        onResize(clamped);
      };

      const handleMouseUp = () => {
        isDragging.current = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        window.removeEventListener("mousemove", handleMouseMove);
        window.removeEventListener("mouseup", handleMouseUp);
      };

      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    },
    [onResize, minWidth, maxWidth]
  );

  const handleDoubleClick = useCallback(() => {
    onResize(400); // reset to default
  }, [onResize]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isDragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, []);

  return (
    <div
      ref={handleRef}
      onMouseDown={handleMouseDown}
      onDoubleClick={handleDoubleClick}
      className={cn(
        "relative z-10 w-1 shrink-0 cursor-col-resize select-none",
        "before:absolute before:inset-y-0 before:-left-1 before:-right-1 before:content-['']",
        "group",
        className
      )}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize panel"
      title="Drag to resize · Double-click to reset"
    >
      {/* Visual indicator line */}
      <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border/60 transition-colors group-hover:bg-primary/40 group-active:bg-primary/60" />

      {/* Center grip dots — visible on hover */}
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        <span className="h-1 w-1 rounded-full bg-primary/40" />
        <span className="h-1 w-1 rounded-full bg-primary/40" />
        <span className="h-1 w-1 rounded-full bg-primary/40" />
      </div>
    </div>
  );
}
