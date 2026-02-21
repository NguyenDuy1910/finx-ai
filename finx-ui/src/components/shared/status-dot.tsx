import { cn } from "@/lib/utils";
import type { HealthStatus } from "@/hooks/use-health-check";

interface StatusDotProps {
  status: HealthStatus;
}

export function StatusDot({ status }: StatusDotProps) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full",
        status === "connected" && "bg-green-500",
        status === "degraded" && "bg-yellow-500",
        status === "disconnected" && "bg-red-500",
        status === "checking" && "animate-pulse bg-muted-foreground/40"
      )}
      title={status}
    />
  );
}
