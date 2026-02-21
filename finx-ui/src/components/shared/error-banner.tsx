import { XCircle } from "lucide-react";
import { Card } from "@/components/ui/card";

interface ErrorBannerProps {
  message: string;
  children?: React.ReactNode;
}

export function ErrorBanner({ message, children }: ErrorBannerProps) {
  return (
    <Card className="border-destructive/30 bg-destructive/5 p-4">
      <div className="flex items-start gap-3">
        <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
        <p className="flex-1 text-sm text-destructive">{message}</p>
        {children}
      </div>
    </Card>
  );
}
