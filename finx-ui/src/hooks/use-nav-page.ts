"use client";

import { useState, useCallback, useEffect } from "react";
import type { NavPage, AdminTab } from "@/types/common.types";
import { ADMIN_TABS } from "@/types/common.types";

// ── Path ↔ Page mapping ──────────────────────────────────────

/** Map URL pathnames → NavPage */
const PATH_TO_PAGE: Record<string, NavPage> = {
  "/": "chat",
  "/chat": "chat",
  "/explore": "explore",
  "/schema-pipeline": "schema-pipeline",
  "/graph-explorer": "graph-explorer",
  "/knowledge": "knowledge",
};

/** Map NavPage → canonical URL pathname */
const PAGE_TO_PATH: Record<NavPage, string> = {
  chat: "/",
  explore: "/explore",
  "schema-pipeline": "/schema-pipeline",
  "graph-explorer": "/graph-explorer",
  knowledge: "/knowledge",
};

/** Default admin sub-tab when none is specified */
const DEFAULT_ADMIN_TAB: AdminTab = "search";

/** Derive NavPage from the current pathname */
function parsePathname(pathname: string): { page: NavPage; adminTab: AdminTab } {
  // Normalise: remove trailing slash (except for "/")
  const normalised = pathname === "/" ? "/" : pathname.replace(/\/$/, "");

  return {
    page: PATH_TO_PAGE[normalised] ?? "chat",
    adminTab: DEFAULT_ADMIN_TAB,
  };
}

/**
 * Hook that keeps `activePage` and `adminTab` in sync with the browser URL.
 *
 * - On mount it reads the current pathname → sets the correct page & admin tab.
 * - `setPage(page)` pushes a new URL so the address-bar updates.
 * - `setAdminTab(tab)` pushes `/admin/<tab>` to the address-bar.
 * - Handles browser back/forward via the `popstate` event.
 */
export function useNavPage() {
  // Always initialise with defaults so the server and first client render agree.
  // The mount useEffect below will immediately sync with the real URL.
  const [activePage, setActivePage] = useState<NavPage>("chat");
  const [adminTab, setAdminTabState] = useState<AdminTab>(DEFAULT_ADMIN_TAB);

  // On mount: read the real pathname (handles SSR hydration mismatch)
  useEffect(() => {
    const { page, adminTab: tab } = parsePathname(window.location.pathname);
    setActivePage(page);
    setAdminTabState(tab);
  }, []);

  // Listen for back/forward navigation
  useEffect(() => {
    const handlePopState = () => {
      const { page, adminTab: tab } = parsePathname(window.location.pathname);
      setActivePage(page);
      setAdminTabState(tab);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  /** Navigate to a top-level page – updates URL + state */
  const setPage = useCallback((page: NavPage) => {
    const targetPath = PAGE_TO_PATH[page];
    if (window.location.pathname !== targetPath) {
      window.history.pushState(null, "", targetPath);
    }
    setActivePage(page);
  }, []);

  /** Navigate to an admin sub-tab – updates URL + state (legacy compat) */
  const setAdminTab = useCallback((tab: AdminTab) => {
    setAdminTabState(tab);
  }, []);

  return { activePage, setPage, adminTab, setAdminTab } as const;
}
