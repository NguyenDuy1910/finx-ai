"use client";

import { useState, useCallback, useEffect, useMemo, lazy, Suspense } from "react";
import { Header } from "@/components/layout/header";
import { Sidebar } from "@/components/layout/sidebar";
import { ChatContainer } from "@/components/chat/chat-container";
import { Loader2 } from "lucide-react";
import {
  AVAILABLE_DATABASES,
  type ChatThread,
  type NavPage,
} from "@/types";
import {
  createThread,
  updateThread,
  titleFromMessage,
} from "@/lib/chat-store";

// ── Lazy-loaded non-chat pages (code-split) ──────────────────
const ExploreContainer = lazy(() =>
  import("@/components/explore/explore-container").then((m) => ({
    default: m.ExploreContainer,
  }))
);
const PlaygroundContainer = lazy(() =>
  import("@/components/playground/playground-container").then((m) => ({
    default: m.PlaygroundContainer,
  }))
);
const AdminContainer = lazy(() =>
  import("@/components/admin/admin-container").then((m) => ({
    default: m.AdminContainer,
  }))
);

/** Suspense fallback for lazy-loaded pages */
function PageLoader() {
  return (
    <div className="flex h-full items-center justify-center animate-fade-in">
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-6 w-6 animate-spin text-primary/60" />
        <span className="text-xs text-muted-foreground">Loading…</span>
      </div>
    </div>
  );
}

export default function Home() {
  const [database, setDatabase] = useState(AVAILABLE_DATABASES[0]);
  const [activePage, setActivePage] = useState<NavPage>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // ── Thread management ──────────────────────────────────────
  const [activeThread, setActiveThread] = useState<ChatThread | null>(null);
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);

  // Create an initial thread on mount
  useEffect(() => {
    if (!activeThread) {
      const t = createThread("agent");
      setActiveThread(t);
      setSidebarRefreshKey((k) => k + 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Close mobile sidebar on page change
  useEffect(() => {
    setSidebarOpen(false);
  }, [activePage]);

  // Lock body scroll when mobile sidebar is open
  useEffect(() => {
    if (sidebarOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [sidebarOpen]);

  const handleNewChat = useCallback(() => {
    const t = createThread("agent");
    setActiveThread(t);
    setSidebarRefreshKey((k) => k + 1);
    setSidebarOpen(false);
  }, []);

  const handleSelectThread = useCallback((thread: ChatThread) => {
    setActiveThread(thread);
    setSidebarOpen(false);
  }, []);

  const handlePageChange = useCallback((page: NavPage) => {
    setActivePage(page);
  }, []);

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev);
  }, []);

  // Called when the backend assigns a session_id for the current thread
  const handleSessionEstablished = useCallback(
    (sessionId: string) => {
      if (!activeThread) return;
      updateThread(activeThread.id, { sessionId });
      setActiveThread((prev) =>
        prev ? { ...prev, sessionId } : prev
      );
      setSidebarRefreshKey((k) => k + 1);
    },
    [activeThread]
  );

  // Called when the user sends the first message — derive thread title
  const handleFirstMessage = useCallback(
    (message: string) => {
      if (!activeThread) return;
      const title = titleFromMessage(message);
      updateThread(activeThread.id, { title });
      setActiveThread((prev) =>
        prev ? { ...prev, title } : prev
      );
      setSidebarRefreshKey((k) => k + 1);
    },
    [activeThread]
  );

  // ── Memoised page content to avoid re-renders ──────────────
  const isChatPage = activePage === "chat";

  const pageContent = useMemo(() => {
    switch (activePage) {
      case "chat":
        return activeThread ? (
          <ChatContainer
            key={activeThread.id}
            threadId={activeThread.id}
            initialSessionId={activeThread.sessionId}
            database={database}
            onSessionEstablished={handleSessionEstablished}
            onFirstMessage={handleFirstMessage}
          />
        ) : null;
      case "explore":
        return (
          <Suspense fallback={<PageLoader />}>
            <ExploreContainer database={database} />
          </Suspense>
        );
      case "playground":
        return (
          <Suspense fallback={<PageLoader />}>
            <PlaygroundContainer database={database} />
          </Suspense>
        );
      case "admin":
        return (
          <Suspense fallback={<PageLoader />}>
            <AdminContainer />
          </Suspense>
        );
      default:
        return null;
    }
  }, [activePage, activeThread, database, handleSessionEstablished, handleFirstMessage]);

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      {/* ── Fixed header ──────────────────────────────────────── */}
      <Header
        database={database}
        onDatabaseChange={setDatabase}
        onNewChat={handleNewChat}
        activePage={activePage}
        onPageChange={handlePageChange}
        onToggleSidebar={handleToggleSidebar}
        showSidebarToggle={isChatPage}
      />

      {/* ── Content area ──────────────────────────────────────── */}
      <div className="relative flex flex-1 overflow-hidden">
        {/* Mobile sidebar overlay */}
        {isChatPage && sidebarOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px] sidebar-overlay lg:hidden"
            style={{ top: "var(--header-height, 56px)" }}
            onClick={() => setSidebarOpen(false)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setSidebarOpen(false);
            }}
            role="button"
            tabIndex={-1}
            aria-label="Close sidebar"
          />
        )}

        {/* Sidebar – slide-in drawer on mobile, static on desktop */}
        {isChatPage && (
          <aside
            className={`
              fixed inset-y-0 left-0 z-50 w-[var(--sidebar-width,280px)] transform transition-transform duration-250 ease-out will-change-transform
              lg:relative lg:z-auto lg:translate-x-0 lg:transition-none
              ${sidebarOpen ? "translate-x-0 shadow-2xl lg:shadow-none" : "-translate-x-full"}
            `}
            style={{ top: "var(--header-height, 56px)" }}
            aria-label="Chat sidebar"
          >
            <Sidebar
              activeThreadId={activeThread?.id ?? null}
              onSelectThread={handleSelectThread}
              onNewChat={handleNewChat}
              refreshKey={sidebarRefreshKey}
            />
          </aside>
        )}

        {/* Main page content */}
        <main
          className="relative flex-1 overflow-hidden animate-page-in"
          key={activePage}
        >
          {pageContent}
        </main>
      </div>
    </div>
  );
}
