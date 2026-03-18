"use client";

import {
  Database,
  CheckCircle2,
  Circle,
  ChevronRight,
} from "lucide-react";
import { PIPELINE_STEPS, type PipelineStep } from "@/types/schema-pipeline.types";
import { cn } from "@/lib/utils";

interface PipelineStepperProps {
  currentStep: PipelineStep;
  completedSteps: Set<PipelineStep>;
  onStepClick: (step: PipelineStep) => void;
  canGoToStep: (step: PipelineStep) => boolean;
}

export function PipelineStepper({
  currentStep,
  completedSteps,
  onStepClick,
  canGoToStep,
}: PipelineStepperProps) {
  return (
    <nav className="mb-8">
      <ol className="flex items-center gap-1 overflow-x-auto pb-2">
        {PIPELINE_STEPS.map((step, idx) => {
          const isActive = currentStep === step.key;
          const isCompleted = completedSteps.has(step.key);
          const isClickable = canGoToStep(step.key) || isCompleted;

          return (
            <li key={step.key} className="flex items-center">
              {idx > 0 && (
                <ChevronRight className="mx-1 h-4 w-4 shrink-0 text-muted-foreground/40" />
              )}
              <button
                onClick={() => isClickable && onStepClick(step.key)}
                disabled={!isClickable}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all whitespace-nowrap",
                  isActive &&
                    "bg-primary text-primary-foreground shadow-sm",
                  isCompleted &&
                    !isActive &&
                    "bg-green-500/10 text-green-600 dark:text-green-400 hover:bg-green-500/20",
                  !isActive &&
                    !isCompleted &&
                    isClickable &&
                    "text-muted-foreground hover:bg-accent hover:text-foreground",
                  !isActive &&
                    !isCompleted &&
                    !isClickable &&
                    "text-muted-foreground/40 cursor-not-allowed"
                )}
              >
                {isCompleted ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0" />
                ) : (
                  <span
                    className={cn(
                      "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold",
                      isActive
                        ? "border-primary-foreground text-primary-foreground"
                        : "border-muted-foreground/40 text-muted-foreground/60"
                    )}
                  >
                    {idx + 1}
                  </span>
                )}
                <span className="hidden sm:inline">{step.label}</span>
              </button>
            </li>
          );
        })}
      </ol>
      {/* Active step description */}
      <p className="text-xs text-muted-foreground mt-1">
        {PIPELINE_STEPS.find((s) => s.key === currentStep)?.description}
      </p>
    </nav>
  );
}
