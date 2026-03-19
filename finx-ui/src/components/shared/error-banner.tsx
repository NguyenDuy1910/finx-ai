import { AlertTriangle } from "lucide-react";

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
  children?: React.ReactNode;
}

export function ErrorBanner({ message, onRetry, children }: ErrorBannerProps) {
  return (
    <div className="rounded-xl border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/5 p-4 animate-fade-in">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600 dark:text-red-400" />
        <div className="min-w-0 flex-1">
          <p className="text-[0.875rem] font-medium text-red-800 dark:text-red-200">
            {message}
          </p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-2 text-[0.8125rem] font-medium text-red-700 dark:text-red-300 underline decoration-red-300 dark:decoration-red-500/30 underline-offset-2 hover:text-red-900 dark:hover:text-red-100"
            >
              Try again
            </button>
          )}
        </div>
        {children}
      </div>
    </div>
  );
}
