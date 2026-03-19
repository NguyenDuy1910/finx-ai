"use client";

import { Bot, Users, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMode } from "@/types/common.types";
import { CHAT_MODE_LABELS, CHAT_MODE_DESCRIPTIONS } from "@/types/common.types";

interface ChatModeSwitcherProps {
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
  isDisabled?: boolean;
}

const MODE_CONFIG: Record<ChatMode, { icon: typeof Bot; color: string; activeColor: string }> = {
  agent: {
    icon: Bot,
    color: "text-blue-500 bg-blue-50 dark:bg-blue-500/10",
    activeColor: "bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300 ring-1 ring-blue-200 dark:ring-blue-500/25",
  },
  team: {
    icon: Users,
    color: "text-violet-500 bg-violet-50 dark:bg-violet-500/10",
    activeColor: "bg-violet-100 dark:bg-violet-500/15 text-violet-700 dark:text-violet-300 ring-1 ring-violet-200 dark:ring-violet-500/25",
  },
  knowledge: {
    icon: BookOpen,
    color: "text-emerald-500 bg-emerald-50 dark:bg-emerald-500/10",
    activeColor: "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 ring-1 ring-emerald-200 dark:ring-emerald-500/25",
  },
};

export function ChatModeSwitcher({ mode, onModeChange, isDisabled }: ChatModeSwitcherProps) {
  return (
    <div className="flex items-center gap-0.5 rounded-lg border border-border bg-muted/50 p-0.5">
      {(Object.keys(MODE_CONFIG) as ChatMode[]).map((key) => {
        const config = MODE_CONFIG[key];
        const Icon = config.icon;
        const isActive = mode === key;

        return (
          <button
            key={key}
            type="button"
            onClick={() => onModeChange(key)}
            disabled={isDisabled}
            title={CHAT_MODE_DESCRIPTIONS[key]}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[0.8125rem] font-medium transition-all duration-100",
              isActive
                ? config.activeColor
                : "text-muted-foreground hover:bg-background hover:text-foreground",
              isDisabled && "pointer-events-none opacity-50"
            )}
            aria-pressed={isActive}
            aria-label={`Switch to ${CHAT_MODE_LABELS[key]} mode`}
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{CHAT_MODE_LABELS[key]}</span>
          </button>
        );
      })}
    </div>
  );
}
