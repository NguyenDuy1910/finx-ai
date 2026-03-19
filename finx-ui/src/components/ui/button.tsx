import { ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "ghost" | "outline";
  size?: "default" | "sm" | "lg" | "icon";
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:pointer-events-none disabled:opacity-50",
          variant === "default" &&
            "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90",
          variant === "ghost" &&
            "hover:bg-accent hover:text-accent-foreground",
          variant === "outline" &&
            "border border-border bg-surface hover:bg-accent hover:text-accent-foreground",
          size === "default" && "h-9 px-4 py-2 text-[0.8125rem]",
          size === "sm" && "h-8 px-3 text-[0.75rem]",
          size === "lg" && "h-11 px-6 text-[0.9375rem]",
          size === "icon" && "h-9 w-9",
          className
        )}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";

export { Button };
