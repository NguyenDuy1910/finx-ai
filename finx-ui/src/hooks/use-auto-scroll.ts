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
    if (autoScroll) {
      // Use instant scroll for auto-scroll during streaming to avoid jank
      bottomRef.current?.scrollIntoView({ behavior: "instant" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { bottomRef, scrollContainerRef, showScrollBtn, handleScroll, scrollToBottom };
}
