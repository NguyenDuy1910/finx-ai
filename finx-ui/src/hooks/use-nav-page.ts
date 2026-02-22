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
  "/playground": "playground",
  "/admin": "admin",
};

/** Map NavPage → canonical URL pathname */
const PAGE_TO_PATH: Record<NavPage, string> = {
  chat: "/",
  explore: "/explore",
  playground: "/playground",
  admin: "/admin",
};

/** Default admin sub-tab when none is specified */
const DEFAULT_ADMIN_TAB: AdminTab = "search";

/** Derive NavPage + AdminTab from the current pathname */
function parsePathname(pathname: string): { page: NavPage; adminTab: AdminTab } {
  // Normalise: remove trailing slash (except for "/")
  const normalised = pathname === "/" ? "/" : pathname.replace(/\/$/, "");

  // Check for /admin/<sub-tab>
  const adminMatch = normalised.match(/^\/admin\/(.+)$/);
  if (adminMatch) {
    const sub = adminMatch[1] as AdminTab;
    return {
      page: "admin",
      adminTab: ADMIN_TABS.includes(sub) ? sub : DEFAULT_ADMIN_TAB,
    };
  }

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
  const [activePage, setActivePage] = useState<NavPage>(() => {
    if (typeof window === "undefined") return "chat";
    return parsePathname(window.location.pathname).page;
  });

  const [adminTab, setAdminTabState] = useState<AdminTab>(() => {
    if (typeof window === "undefined") return DEFAULT_ADMIN_TAB;
    return parsePathname(window.location.pathname).adminTab;
  });

  // On mount: read the real pathname (handles SSR hydration mismatch)
  // Also redirect bare /admin → /admin/search
  useEffect(() => {
    const { page, adminTab: tab } = parsePathname(window.location.pathname);
    setActivePage(page);
    setAdminTabState(tab);

    // If user lands on bare /admin, replace URL with /admin/<default>
    const normalised = window.location.pathname.replace(/\/$/, "");
    if (normalised === "/admin") {
      window.history.replaceState(null, "", `/admin/${DEFAULT_ADMIN_TAB}`);
    }
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
    if (page === "admin") {
      // When navigating to admin, preserve the current admin tab
      const fullPath = `/admin/${DEFAULT_ADMIN_TAB}`;
      if (window.location.pathname !== fullPath) {
        window.history.pushState(null, "", fullPath);
      }
      setAdminTabState(DEFAULT_ADMIN_TAB);
    } else {
      if (window.location.pathname !== targetPath) {
        window.history.pushState(null, "", targetPath);
      }
    }
    setActivePage(page);
  }, []);

  /** Navigate to an admin sub-tab – updates URL + state */
  const setAdminTab = useCallback((tab: AdminTab) => {
    const targetPath = `/admin/${tab}`;
    if (window.location.pathname !== targetPath) {
      window.history.pushState(null, "", targetPath);
    }
    setAdminTabState(tab);
    setActivePage("admin");
  }, []);

  return { activePage, setPage, adminTab, setAdminTab } as const;
}
