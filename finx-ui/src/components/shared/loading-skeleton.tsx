import { Skeleton } from "@/components/ui/skeleton";

interface LoadingSkeletonProps {
  /** Number of skeleton rows */
  count?: number;
  className?: string;
  /** Use a chat-message style skeleton */
  variant?: "default" | "chat";
}

export function LoadingSkeleton({ count = 3, className, variant = "default" }: LoadingSkeletonProps) {
  if (variant === "chat") {
    return (
      <div className="space-y-4 px-4 py-6">
        {Array.from({ length: count }).map((_, i) => (
          <div key={i} className="flex gap-3 animate-fade-in" style={{ animationDelay: `${i * 80}ms` }}>
            <Skeleton className="h-6 w-6 shrink-0 rounded-md" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-4 w-full max-w-[400px]" />
              <Skeleton className="h-4 w-3/4 max-w-[300px]" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton
          key={i}
          className={className ?? "h-16 w-full rounded-xl"}
          style={{ animationDelay: `${i * 50}ms` }}
        />
      ))}
    </div>
  );
}
