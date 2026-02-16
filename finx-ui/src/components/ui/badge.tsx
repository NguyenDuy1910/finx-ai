import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "success" | "warning" | "destructive";
}

function Badge({
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
        variant === "default" && "bg-primary/10 text-primary",
        variant === "success" && "bg-green-500/10 text-green-600 dark:text-green-400",
        variant === "warning" && "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400",
        variant === "destructive" && "bg-red-500/10 text-red-600 dark:text-red-400",
        className
      )}
      {...props}
    />
  );
}

export { Badge };
