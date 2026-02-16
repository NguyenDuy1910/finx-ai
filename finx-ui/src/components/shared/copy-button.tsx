"use client";

import { Copy, Check } from "lucide-react";
import { useClipboard } from "@/hooks/use-clipboard";
import { Button } from "@/components/ui/button";

interface CopyButtonProps {
  text: string;
  label?: string;
  className?: string;
}

export function CopyButton({ text, label, className }: CopyButtonProps) {
  const { copied, copy } = useClipboard();

  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={() => copy(text)}
      className={className ?? "h-7 gap-1.5 text-xs"}
    >
      {copied ? (
        <Check className="h-3 w-3 text-green-500" />
      ) : (
        <Copy className="h-3 w-3" />
      )}
      {label !== undefined ? (copied ? "Copied" : label) : null}
    </Button>
  );
}
