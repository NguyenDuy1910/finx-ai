"use client";

import { useRef, useState, useCallback, useEffect, type RefObject } from "react";

export function useAutoScroll(deps: unknown[]): {
  bottomRef: RefObject<HTMLDivElement | null>;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
  showScrollBtn: boolean;
  handleScroll: () => void;
  scrollToBottom: () => void;
} {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  // RAF guard — only one scroll per animation frame even when deps change many
  // times between paints (fast streaming tokens).
  const rafRef = useRef<number | null>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    setAutoScroll(true);
    setShowScrollBtn(false);
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    setAutoScroll(isNearBottom);
    setShowScrollBtn(!isNearBottom);
  }, []);

  useEffect(() => {
    if (!autoScroll) return;

    // Coalesce multiple dependency changes into a single rAF scroll
    if (rafRef.current != null) return;

    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      bottomRef.current?.scrollIntoView({ behavior: "instant" });
    });

    return () => {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { bottomRef, scrollContainerRef, showScrollBtn, handleScroll, scrollToBottom };
}
