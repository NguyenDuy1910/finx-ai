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
          "inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
          variant === "default" &&
            "bg-primary text-primary-foreground hover:bg-primary/90",
          variant === "ghost" &&
            "hover:bg-accent hover:text-accent-foreground",
          variant === "outline" &&
            "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
          size === "default" && "h-10 px-4 py-2 text-sm",
          size === "sm" && "h-8 px-3 text-xs",
          size === "lg" && "h-12 px-6 text-base",
          size === "icon" && "h-10 w-10",
          className
        )}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";

export { Button };
