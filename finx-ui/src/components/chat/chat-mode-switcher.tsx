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
    color: "text-blue-500 bg-blue-500/8 ring-blue-500/20",
    activeColor: "bg-blue-500/15 text-blue-600 ring-blue-500/30 dark:text-blue-400",
  },
  team: {
    icon: Users,
    color: "text-violet-500 bg-violet-500/8 ring-violet-500/20",
    activeColor: "bg-violet-500/15 text-violet-600 ring-violet-500/30 dark:text-violet-400",
  },
  knowledge: {
    icon: BookOpen,
    color: "text-emerald-500 bg-emerald-500/8 ring-emerald-500/20",
    activeColor: "bg-emerald-500/15 text-emerald-600 ring-emerald-500/30 dark:text-emerald-400",
  },
};

export function ChatModeSwitcher({ mode, onModeChange, isDisabled }: ChatModeSwitcherProps) {
  return (
    <div className="flex items-center gap-1 rounded-lg bg-muted/50 p-0.5">
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
              "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium ring-1 transition-all duration-150",
              isActive
                ? config.activeColor
                : "text-muted-foreground ring-transparent hover:bg-background/60 hover:text-foreground",
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
